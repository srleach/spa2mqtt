#include "spa_bus.h"

#include <cinttypes>
#include <cmath>

#include "esphome/core/log.h"

namespace esphome {
namespace spa_bus {

static const char *const TAG = "spa_bus";
static const uint32_t STATUS_TIMEOUT_MS = 10000;  // docs/protocol.md §7

#ifdef USE_BUTTON
void SpaButton::press_action() {
  if (this->parent_ != nullptr) this->parent_->press(this->code_);
}
#endif

#ifdef USE_NUMBER
void SpaNumber::control(float value) {
  if (this->parent_ != nullptr) this->parent_->set_setpoint(this->index_, value);
}

void SpaBus::register_setpoint(SpaNumber *n, size_t field, int mode_field, uint8_t up, uint8_t down, float step,
                               float min, float max, uint16_t confirm_frames, uint16_t max_attempts) {
  spa_proto::SetpointController sp;
  sp.up = up;
  sp.down = down;
  sp.step = step;
  sp.minimum = min;
  sp.maximum = max;
  sp.confirm_frames = confirm_frames;
  sp.max_attempts = max_attempts;
  n->set_parent(this, this->core_.setpoints.size());
  this->core_.setpoints.push_back({field, mode_field, sp});
  this->numbers_.push_back({field, n});
}
#endif

bool SpaBus::press(uint8_t code) {
  if (!this->transmit_) {
    ESP_LOGW(TAG, "transmit disabled (spa_bus.transmit: false); ignoring press 0x%02X", code);
    return false;
  }
  ESP_LOGI(TAG, "queueing press 0x%02X", code);
  return this->core_.bus.enqueue_press(code);
}

bool SpaBus::set_setpoint(size_t index, float value) {
  if (!this->transmit_) {
    ESP_LOGW(TAG, "transmit disabled (spa_bus.transmit: false); ignoring setpoint %.1f", value);
    return false;
  }
  if (index >= this->core_.setpoints.size()) return false;
  float target = this->core_.setpoints[index].ctl.set_target(value);
  ESP_LOGI(TAG, "setpoint target %.1f", target);
  return true;
}

void SpaBus::setup() {
  if (this->flow_control_pin_ != nullptr) {
    this->flow_control_pin_->setup();
    this->flow_control_pin_->digital_write(false);
  }
  this->publish_bus_state_();
}

void SpaBus::loop() {
  uint8_t buf[64];
  size_t avail;
  while ((avail = this->available()) > 0) {
    size_t n = avail < sizeof(buf) ? avail : sizeof(buf);
    if (!this->read_array(buf, n)) break;
    for (size_t i = 0; i < n; i++) {
      if (this->decoder_.push(buf[i])) this->handle_frame_(this->decoder_.frame());
    }
  }
  const uint32_t now = millis();
  if (this->online_ && now - this->last_status_ms_ > STATUS_TIMEOUT_MS) {
    this->online_ = false;
    ESP_LOGW(TAG, "no status frames for %" PRIu32 " ms", STATUS_TIMEOUT_MS);
    this->publish_bus_state_();
  }
  if (this->online_ && now - this->last_heartbeat_ >= this->heartbeat_ms_) {
    this->last_heartbeat_ = now;
    this->publish_(true);
  }
}

void SpaBus::handle_frame_(const spa_proto::Frame &frame) {
  std::vector<spa_proto::Frame> tx;
  const bool status = this->core_.on_frame(frame, tx);
  for (const auto &out : tx) this->transmit_frame_(out);
  if (status) {
    this->last_status_ms_ = millis();
    if (!this->online_) {
      this->online_ = true;
      ESP_LOGI(TAG, "receiving status frames");
    }
    this->publish_(false);
  }
  if (this->core_.bus.state != this->published_state_) this->publish_bus_state_();
}

// TRANSMITS: the only place this component writes to the bus. BusClient never produces
// frames while transmit is disabled; this guard is defence in depth.
void SpaBus::transmit_frame_(const spa_proto::Frame &frame) {
  if (!this->transmit_) return;
  uint8_t wire[spa_proto::MAX_LEN + 2];
  const size_t n = frame.encode(wire);
  if (this->flow_control_pin_ != nullptr) this->flow_control_pin_->digital_write(true);
  this->write_array(wire, n);
  this->flush();
  if (this->flow_control_pin_ != nullptr) this->flow_control_pin_->digital_write(false);
  ESP_LOGD(TAG, "TX addr=0x%02X type=0x%02X len=%u", frame.addr, frame.type, frame.payload_len);
}

void SpaBus::publish_(bool force) {
  const auto &values = this->core_.values;
  const auto &changed = this->core_.changed;
#ifdef USE_SENSOR
  for (auto &b : this->sensors_)
    if (force || changed[b.first])
      b.second->publish_state(values[b.first].valid ? values[b.first].number : NAN);
#endif
#ifdef USE_BINARY_SENSOR
  for (auto &b : this->binary_sensors_)
    if ((force || changed[b.first]) && values[b.first].valid) b.second->publish_state(values[b.first].b);
#endif
#ifdef USE_TEXT_SENSOR
  for (auto &b : this->text_sensors_) {
    if (!(force || changed[b.first])) continue;
    const auto &v = values[b.first];
    if (!v.valid) b.second->publish_state("unknown");
    else if (v.text != nullptr) b.second->publish_state(*v.text);
    else b.second->publish_state(to_string(static_cast<int>(v.number)));
  }
#endif
#ifdef USE_NUMBER
  for (auto &b : this->numbers_)
    if ((force || changed[b.first]) && values[b.first].valid) b.second->publish_state(values[b.first].number);
#endif
}

void SpaBus::publish_bus_state_() {
  this->published_state_ = this->core_.bus.state;
#ifdef USE_TEXT_SENSOR
  if (this->bus_state_sensor_ == nullptr) return;
  std::string s = !this->online_ ? "no status" : (this->transmit_ ? spa_proto::bus_state_name(this->core_.bus.state)
                                                                   : "receive-only");
  if (this->transmit_ && this->core_.bus.channel >= 0) {
    char ch[12];
    snprintf(ch, sizeof(ch), " (0x%02X)", this->core_.bus.channel);
    s += ch;
  }
  this->bus_state_sensor_->publish_state(s);
#endif
}

void SpaBus::dump_config() {
  ESP_LOGCONFIG(TAG, "Spa bus:");
  ESP_LOGCONFIG(TAG, "  Transmit: %s", this->transmit_ ? "ENABLED" : "disabled (receive-only)");
  ESP_LOGCONFIG(TAG, "  Fields: %u", static_cast<unsigned>(this->core_.fields.size()));
  ESP_LOGCONFIG(TAG, "  Heartbeat: %" PRIu32 " ms", this->heartbeat_ms_);
  LOG_PIN("  Flow control pin: ", this->flow_control_pin_);
  ESP_LOGCONFIG(TAG, "  Frames: %" PRIu32 ", CRC errors: %" PRIu32, this->decoder_.stats.frames,
                this->decoder_.stats.crc_errors);
  this->check_uart_settings(this->expected_baud_);
}

}  // namespace spa_bus
}  // namespace esphome
