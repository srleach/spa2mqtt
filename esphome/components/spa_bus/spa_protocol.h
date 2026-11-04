// Framework-free core of the spa_bus component: CRC, framing, cipher, field decode, bus
// arbitration and setpoint control. No ESPHome headers, so it is compiled and tested on the
// host (tests/cpp) against the same capture fixtures as the Python bridge.
//
// Semantics mirror spa2mqtt/protocol, spa2mqtt/definitions/model.py (FieldDef.decode),
// spa2mqtt/tub/bus.py and spa2mqtt/tub/control.py. See docs/protocol.md and docs/design.md.
#pragma once

#include <cstddef>
#include <cstdint>
#include <deque>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace spa_proto {

constexpr uint8_t FLAG = 0x7E;
constexpr uint8_t MIN_LEN = 5;
constexpr uint8_t MAX_LEN = 64;
constexpr size_t MAX_PAYLOAD = MAX_LEN - MIN_LEN;

uint8_t crc8(const uint8_t *data, size_t len);

struct Frame {
  uint8_t addr{0};
  uint8_t mid{0};
  uint8_t type{0};
  uint8_t payload_len{0};
  uint8_t payload[MAX_PAYLOAD]{};
  // Serialise to wire bytes; returns the number of bytes written to out (max MAX_LEN + 2).
  size_t encode(uint8_t *out) const;
};

struct DecoderStats {
  uint32_t frames{0};
  uint32_t crc_errors{0};
  uint32_t resyncs{0};
  uint32_t bytes_dropped{0};
};

// Same algorithm as spa2mqtt.protocol.framing.FrameDecoder: frames by LEN, verifies end flag
// and CRC, leaves the closing flag in place (it may be shared as the next start flag).
class FrameDecoder {
 public:
  // Push one byte. Returns true when a frame was completed; read it with frame().
  bool push(uint8_t byte);
  const Frame &frame() const { return frame_; }
  DecoderStats stats;

 private:
  bool scan_();
  uint8_t buf_[2 * (MAX_LEN + 2)]{};
  size_t n_{0};
  Frame frame_;
};

// Status payload fold: d[j] = p[2j] ^ p[2j+1] ^ 1. Returns decoded length.
size_t fold(const uint8_t *payload, size_t len, uint8_t *out);
// Remove the per-frame key: out[i] = p[i] ^ p[0] (out[0] = 0). Returns len. protocol.md §3.3.
size_t unkey(const uint8_t *payload, size_t len, uint8_t *out);

enum class StatusDecode : uint8_t { FOLD, UNKEY, DECRYPT };
void cc_encode(uint8_t code, uint8_t key, uint8_t out[2]);
int cc_decode(const uint8_t *payload, size_t len);  // -1 if too short

enum class FieldKind : uint8_t { BOOL, NUMBER, ENUM };

struct FieldDef {
  uint8_t byte{0};
  uint8_t length{1};
  uint32_t xor_{0};
  int8_t bit{-1};
  uint8_t shift{0};
  uint32_t mask{0xFFFFFFFF};
  bool has_scale{false};
  float scale{1.0f};
  float offset{0.0f};
  std::vector<uint32_t> invalid;
  std::vector<std::pair<uint32_t, std::string>> map;

  FieldKind kind() const {
    if (bit >= 0) return FieldKind::BOOL;
    if (!map.empty()) return FieldKind::ENUM;
    return FieldKind::NUMBER;
  }
};

struct FieldValue {
  bool valid{false};
  FieldKind kind{FieldKind::NUMBER};
  bool b{false};
  float number{0.0f};
  const std::string *text{nullptr};
  bool operator==(const FieldValue &o) const;
  bool operator!=(const FieldValue &o) const { return !(*this == o); }
};

FieldValue decode_field(const FieldDef &f, const uint8_t *decoded, size_t len);

enum class BusState : uint8_t { LISTEN, CLAIMING, REQUESTED, READY };
const char *bus_state_name(BusState s);

struct BusConfig {
  uint8_t client_mid{0xBF};
  uint8_t magic[2]{0xF1, 0x73};
  uint16_t dormant_threshold{5};
  int command_type{-1};
};

// Sans-IO port of spa2mqtt.tub.bus.BusClient. handle() returns frames to send; it never
// produces any while transmit_enabled is false.
class BusClient {
 public:
  BusConfig config;
  bool transmit_enabled{false};
  BusState state{BusState::LISTEN};
  int channel{-1};
  std::set<uint8_t> polled;
  std::set<uint8_t> active;
  uint32_t commands_seen{0};
  std::deque<uint8_t> queue;

  bool enqueue_press(uint8_t code);  // false if transmit is disabled
  std::vector<Frame> handle(const Frame &f);
  int last_panel_code{0};

 private:
  int dormant_() const;
  bool replied_to_last_cts_{false};
  uint32_t request_age_{0};
};

// Port of spa2mqtt.tub.control.SetpointController.
class SetpointController {
 public:
  uint8_t up{0x01}, down{0x02};
  float step{0.5f}, minimum{0.0f}, maximum{100.0f};
  uint16_t confirm_frames{3}, max_attempts{40};
  bool has_target{false};
  float target{0.0f};
  uint16_t attempts{0};

  uint16_t wake_presses{0};

  float set_target(float value);
  // Called on every status frame. Returns a button code to press, or -1.
  // set_mode: -1 = the tub has no set-mode field, 0/1 = its current value.
  // press_queued: our last press has not been sent yet; do not judge it.
  int on_status(bool valid, float setpoint, int set_mode = -1, bool press_queued = false);

 private:
  bool pending_{false};
  uint16_t wait_{0};
  float at_press_{0.0f};
  int mode_at_press_{-1};
};

}  // namespace spa_proto

namespace spa_proto {

inline FieldDef make_field(uint8_t byte, uint8_t length, uint32_t xor_, int8_t bit, uint8_t shift, uint32_t mask,
                           bool has_scale, float scale, float offset, std::vector<uint32_t> invalid,
                           std::vector<std::pair<uint32_t, std::string>> map) {
  FieldDef f;
  f.byte = byte;
  f.length = length;
  f.xor_ = xor_;
  f.bit = bit;
  f.shift = shift;
  f.mask = mask;
  f.has_scale = has_scale;
  f.scale = scale;
  f.offset = offset;
  f.invalid = std::move(invalid);
  f.map = std::move(map);
  return f;
}

// Everything except I/O and entities: definition tables, decoder, bus and setpoint state.
// SpaBus (ESPHome) and the host test both drive this class.
class SpaCore {
 public:
  void set_status_type(uint8_t type, uint8_t length, StatusDecode decode = StatusDecode::FOLD) {
    status_type_ = type;
    status_length_ = length;
    status_decode_ = decode;
  }
  void set_command_type(uint8_t type) { bus.config.command_type = type; }
  // DECRYPT: plain[i] = unkeyed[i] ^ stream[i] (protocol.md §3.3).
  void set_status_stream(std::vector<uint8_t> stream) { status_stream_ = std::move(stream); }
  void set_bus_params(uint8_t mid, uint8_t m0, uint8_t m1, uint16_t threshold) {
    bus.config.client_mid = mid;
    bus.config.magic[0] = m0;
    bus.config.magic[1] = m1;
    bus.config.dormant_threshold = threshold;
  }
  size_t add_field(FieldDef f) {
    fields.push_back(std::move(f));
    values.emplace_back();
    changed.push_back(false);
    return fields.size() - 1;
  }
  void set_transmit(bool enabled) { bus.transmit_enabled = enabled; }

  // Process one frame. Returns true if it was a valid status frame (values/changed updated).
  // Frames to transmit are appended to tx (always empty unless transmit is enabled).
  bool on_frame(const Frame &f, std::vector<Frame> &tx) {
    auto out = bus.handle(f);
    tx.insert(tx.end(), out.begin(), out.end());
    if (f.type != status_type_ || f.mid != 0xAF) return false;
    uint8_t decoded[MAX_PAYLOAD];
    size_t n;
    if (status_decode_ == StatusDecode::FOLD) {
      n = fold(f.payload, f.payload_len, decoded);
    } else {
      n = unkey(f.payload, f.payload_len, decoded);
      if (status_decode_ == StatusDecode::DECRYPT)
        for (size_t i = 0; i < n && i < status_stream_.size(); i++) decoded[i] ^= status_stream_[i];
    }
    if (n < status_length_) {
      bad_status_frames++;
      return false;
    }
    status_frames++;
    for (size_t i = 0; i < fields.size(); i++) {
      FieldValue v = decode_field(fields[i], decoded, n);
      changed[i] = (status_frames == 1) || v != values[i];
      values[i] = v;
    }
    for (auto &sp : setpoints) {
      const FieldValue &v = values[sp.field];
      int mode = -1;
      if (sp.mode_field >= 0) {
        const FieldValue &m = values[static_cast<size_t>(sp.mode_field)];
        if (m.valid && m.kind == FieldKind::BOOL) mode = m.b ? 1 : 0;
      }
      const int code = sp.ctl.on_status(v.valid && v.kind == FieldKind::NUMBER, v.number, mode, !bus.queue.empty());
      if (code >= 0) bus.enqueue_press(static_cast<uint8_t>(code));
    }
    return true;
  }

  std::vector<FieldDef> fields;
  std::vector<FieldValue> values;
  std::vector<bool> changed;
  struct SetpointBinding {
    size_t field;
    int mode_field;  // -1 when the definition names no set-mode field
    SetpointController ctl;
  };
  std::vector<SetpointBinding> setpoints;
  BusClient bus;
  uint32_t status_frames{0};
  uint32_t bad_status_frames{0};

 private:
  uint8_t status_type_{0xC4};
  uint8_t status_length_{16};
  StatusDecode status_decode_{StatusDecode::FOLD};
  std::vector<uint8_t> status_stream_;
};

}  // namespace spa_proto
