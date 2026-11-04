#include "spa_protocol.h"

#include <cmath>
#include <cstring>

namespace spa_proto {

namespace {
uint8_t crc_table_entry(uint8_t b) {
  uint8_t crc = b;
  for (int i = 0; i < 8; i++) crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x07) : static_cast<uint8_t>(crc << 1);
  return crc;
}
constexpr uint8_t T_NEW_CLIENT_CTS = 0x00;
constexpr uint8_t T_CHANNEL_REQUEST = 0x01;
constexpr uint8_t T_CHANNEL_RESPONSE = 0x02;
constexpr uint8_t T_CHANNEL_ACK = 0x03;
constexpr uint8_t T_CTS = 0x06;
constexpr uint8_t UNASSIGNED = 0xFE;
constexpr uint32_t REQUEST_TIMEOUT_FRAMES = 200;
}  // namespace

uint8_t crc8(const uint8_t *data, size_t len) {
  static uint8_t table[256];
  static bool ready = false;
  if (!ready) {
    for (int i = 0; i < 256; i++) table[i] = crc_table_entry(static_cast<uint8_t>(i));
    ready = true;
  }
  uint8_t crc = 0x02;
  for (size_t i = 0; i < len; i++) crc = table[crc ^ data[i]];
  return crc ^ 0x02;
}

size_t Frame::encode(uint8_t *out) const {
  const uint8_t length = static_cast<uint8_t>(payload_len + MIN_LEN);
  out[0] = FLAG;
  out[1] = length;
  out[2] = addr;
  out[3] = mid;
  out[4] = type;
  std::memcpy(out + 5, payload, payload_len);
  out[5 + payload_len] = crc8(out + 1, 4 + payload_len);
  out[6 + payload_len] = FLAG;
  return 7 + payload_len;
}

bool FrameDecoder::push(uint8_t byte) {
  if (n_ == sizeof(buf_)) {  // cannot happen while scan_ keeps up; be defensive
    stats.bytes_dropped += n_;
    n_ = 0;
  }
  buf_[n_++] = byte;
  return scan_();
}

bool FrameDecoder::scan_() {
  size_t i = 0;
  bool got = false;
  while (i < n_) {
    if (buf_[i] != FLAG) {
      stats.bytes_dropped++;
      i++;
      continue;
    }
    if (i + 1 >= n_) break;
    const uint8_t length = buf_[i + 1];
    if (length == FLAG) {
      i++;
      continue;
    }
    if (length < MIN_LEN || length > MAX_LEN) {
      stats.resyncs++;
      i++;
      continue;
    }
    const size_t end = i + length + 1;
    if (end >= n_) break;  // need more bytes
    if (buf_[end] != FLAG) {
      stats.resyncs++;
      i++;
      continue;
    }
    if (crc8(buf_ + i + 1, length - 1) != buf_[end - 1]) {
      stats.crc_errors++;
      i++;
      continue;
    }
    frame_.addr = buf_[i + 2];
    frame_.mid = buf_[i + 3];
    frame_.type = buf_[i + 4];
    frame_.payload_len = static_cast<uint8_t>(length - MIN_LEN);
    std::memcpy(frame_.payload, buf_ + i + 5, frame_.payload_len);
    stats.frames++;
    got = true;
    i = end;  // keep the closing flag
    break;    // one frame per push: bytes arrive one at a time
  }
  if (i > 0) {
    std::memmove(buf_, buf_ + i, n_ - i);
    n_ -= i;
  }
  return got;
}

size_t fold(const uint8_t *payload, size_t len, uint8_t *out) {
  size_t n = 0;
  for (size_t i = 0; i + 1 < len; i += 2) out[n++] = payload[i] ^ payload[i + 1] ^ 1;
  return n;
}

void cc_encode(uint8_t code, uint8_t key, uint8_t out[2]) {
  out[0] = key;
  out[1] = key ^ 0xE0 ^ code;
}

int cc_decode(const uint8_t *payload, size_t len) {
  if (len < 2) return -1;
  return payload[0] ^ payload[1] ^ 0xE0;
}

bool FieldValue::operator==(const FieldValue &o) const {
  if (valid != o.valid || kind != o.kind) return false;
  if (!valid) return true;
  switch (kind) {
    case FieldKind::BOOL:
      return b == o.b;
    case FieldKind::ENUM:
      return text == o.text;
    case FieldKind::NUMBER:
    default:
      return number == o.number;
  }
}

FieldValue decode_field(const FieldDef &f, const uint8_t *decoded, size_t len) {
  FieldValue v;
  v.kind = f.kind();
  if (static_cast<size_t>(f.byte) + f.length > len) return v;
  uint32_t raw = 0;
  for (uint8_t i = 0; i < f.length; i++) raw = (raw << 8) | decoded[f.byte + i];
  raw ^= f.xor_;
  if (f.bit >= 0) {
    v.valid = true;
    v.b = ((raw >> f.bit) & 1U) != 0;
    return v;
  }
  raw = (raw >> f.shift) & f.mask;
  for (uint32_t inv : f.invalid)
    if (inv == raw) return v;
  if (!f.map.empty()) {
    for (const auto &kv : f.map)
      if (kv.first == raw) {
        v.valid = true;
        v.text = &kv.second;
        return v;
      }
    return v;  // unmapped value: unknown
  }
  v.valid = true;
  v.number = static_cast<float>(raw) * (f.has_scale ? f.scale : 1.0f) + f.offset;
  return v;
}

const char *bus_state_name(BusState s) {
  switch (s) {
    case BusState::LISTEN:
      return "listening";
    case BusState::CLAIMING:
      return "claiming";
    case BusState::REQUESTED:
      return "requested";
    case BusState::READY:
      return "ready";
  }
  return "?";
}

bool BusClient::enqueue_press(uint8_t code) {
  if (!transmit_enabled || config.command_type < 0) return false;
  queue.push_back(code);
  if (state == BusState::LISTEN) state = BusState::CLAIMING;
  return true;
}

int BusClient::dormant_() const {
  for (uint8_t ch : polled)
    if (ch != UNASSIGNED && ch != 0xFF && active.count(ch) == 0) return ch;
  return -1;
}

std::vector<Frame> BusClient::handle(const Frame &f) {
  std::vector<Frame> out;
  if (f.type == T_CTS) {
    polled.insert(f.addr);
    replied_to_last_cts_ = false;
    if (state == BusState::READY && f.addr == channel && !queue.empty()) {
      Frame cc;
      cc.addr = static_cast<uint8_t>(channel);
      cc.mid = config.client_mid;
      cc.type = static_cast<uint8_t>(config.command_type);
      cc.payload_len = 2;
      cc_encode(queue.front(), 0x00, cc.payload);
      queue.pop_front();
      out.push_back(cc);
      replied_to_last_cts_ = true;
    }
  } else if (config.command_type >= 0 && f.type == config.command_type) {
    commands_seen++;
    active.insert(f.addr);
    const int code = cc_decode(f.payload, f.payload_len);
    if (code > 0) last_panel_code = code;
    if (state == BusState::READY && f.addr == channel && !replied_to_last_cts_) {
      channel = -1;
      state = queue.empty() ? BusState::LISTEN : BusState::CLAIMING;
    }
  } else if (f.type == T_NEW_CLIENT_CTS && state == BusState::CLAIMING && dormant_() < 0 &&
             commands_seen >= config.dormant_threshold) {
    Frame req;
    req.addr = UNASSIGNED;
    req.mid = config.client_mid;
    req.type = T_CHANNEL_REQUEST;
    req.payload_len = 3;
    req.payload[0] = 0x02;
    req.payload[1] = config.magic[0];
    req.payload[2] = config.magic[1];
    out.push_back(req);
    state = BusState::REQUESTED;
    request_age_ = 0;
  } else if (f.type == T_CHANNEL_RESPONSE && state == BusState::REQUESTED && f.payload_len > 0) {
    channel = f.payload[0];
    Frame ack;
    ack.addr = static_cast<uint8_t>(channel);
    ack.mid = config.client_mid;
    ack.type = T_CHANNEL_ACK;
    out.push_back(ack);
    state = BusState::READY;
  }

  if (state == BusState::CLAIMING && commands_seen >= config.dormant_threshold) {
    const int d = dormant_();
    if (d >= 0) {
      channel = d;
      state = BusState::READY;
    }
  } else if (state == BusState::REQUESTED) {
    if (++request_age_ > REQUEST_TIMEOUT_FRAMES) state = BusState::CLAIMING;
  }
  if (!transmit_enabled) out.clear();
  return out;
}

float SetpointController::set_target(float value) {
  float clamped = value < minimum ? minimum : (value > maximum ? maximum : value);
  target = std::round(clamped / step) * step;
  has_target = true;
  attempts = 0;
  wake_presses = 0;
  pending_ = false;
  return target;
}

int SetpointController::on_status(bool valid, float setpoint, int set_mode, bool press_queued) {
  if (!has_target || !valid) return -1;
  if (std::fabs(setpoint - target) < step / 2) {
    has_target = false;
    pending_ = false;
    return -1;
  }
  if (pending_) {
    if (press_queued) return -1;
    if (setpoint != at_press_) {
      pending_ = false;
    } else if (set_mode == 1 && mode_at_press_ == 0) {
      wake_presses++;  // the press only opened the set screen; step now
      pending_ = false;
    } else {
      if (--wait_ > 0) return -1;
      pending_ = false;
    }
  }
  if (attempts >= max_attempts) {
    has_target = false;
    return -1;
  }
  attempts++;
  pending_ = true;
  wait_ = confirm_frames;
  at_press_ = setpoint;
  mode_at_press_ = set_mode;
  return setpoint < target ? up : down;
}

}  // namespace spa_proto
