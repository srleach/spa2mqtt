#pragma once

#include <vector>

#include "esphome/components/uart/uart.h"
#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#include "esphome/core/hal.h"
#include "spa_protocol.h"

#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif
#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif
#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif
#ifdef USE_BUTTON
#include "esphome/components/button/button.h"
#endif
#ifdef USE_NUMBER
#include "esphome/components/number/number.h"
#endif

namespace esphome {
namespace spa_bus {

class SpaBus;

#ifdef USE_BUTTON
class SpaButton : public button::Button {
 public:
  void set_parent(SpaBus *parent) { parent_ = parent; }
  void set_code(uint8_t code) { code_ = code; }

 protected:
  void press_action() override;
  SpaBus *parent_{nullptr};
  uint8_t code_{0};
};
#endif

#ifdef USE_NUMBER
class SpaNumber : public number::Number {
 public:
  void set_parent(SpaBus *parent, size_t setpoint_index) {
    parent_ = parent;
    index_ = setpoint_index;
  }

 protected:
  void control(float value) override;
  SpaBus *parent_{nullptr};
  size_t index_{0};
};
#endif

class SpaBus : public Component, public uart::UARTDevice {
 public:
  // --- configuration, emitted by codegen from the tub definition ---
  void set_status_type(uint8_t type, uint8_t length) { core_.set_status_type(type, length); }
  void set_command_type(uint8_t type) { core_.set_command_type(type); }
  void set_bus_params(uint8_t mid, uint8_t m0, uint8_t m1, uint16_t threshold) {
    core_.set_bus_params(mid, m0, m1, threshold);
  }
  void add_field(spa_proto::FieldDef f) { core_.add_field(std::move(f)); }
  void set_transmit(bool enabled) {
    transmit_ = enabled;
    core_.set_transmit(enabled);
  }
  void set_heartbeat(uint32_t ms) { heartbeat_ms_ = ms; }
  void set_expected_baud(uint32_t baud) { expected_baud_ = baud; }
  void set_flow_control_pin(GPIOPin *pin) { flow_control_pin_ = pin; }
#ifdef USE_TEXT_SENSOR
  void set_bus_state_sensor(text_sensor::TextSensor *s) { bus_state_sensor_ = s; }
  void register_text_sensor(size_t field, text_sensor::TextSensor *s) { text_sensors_.push_back({field, s}); }
#endif
#ifdef USE_SENSOR
  void register_sensor(size_t field, sensor::Sensor *s) { sensors_.push_back({field, s}); }
#endif
#ifdef USE_BINARY_SENSOR
  void register_binary_sensor(size_t field, binary_sensor::BinarySensor *s) { binary_sensors_.push_back({field, s}); }
#endif
#ifdef USE_NUMBER
  void register_setpoint(SpaNumber *n, size_t field, uint8_t up, uint8_t down, float step, float min, float max,
                         uint16_t confirm_frames, uint16_t max_attempts);
#endif

  // --- commands (no-ops with a warning unless transmit is enabled) ---
  bool press(uint8_t code);
  bool set_setpoint(size_t setpoint_index, float value);

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  void handle_frame_(const spa_proto::Frame &frame);
  void transmit_frame_(const spa_proto::Frame &frame);  // TRANSMITS
  void publish_(bool force);
  void publish_bus_state_();

  spa_proto::SpaCore core_;
  spa_proto::FrameDecoder decoder_;
  bool transmit_{false};
  uint32_t heartbeat_ms_{60000};
  uint32_t expected_baud_{115200};
  uint32_t last_heartbeat_{0};
  uint32_t last_status_ms_{0};
  bool online_{false};
  GPIOPin *flow_control_pin_{nullptr};
  spa_proto::BusState published_state_{spa_proto::BusState::LISTEN};
  bool bus_state_published_{false};
#ifdef USE_SENSOR
  std::vector<std::pair<size_t, sensor::Sensor *>> sensors_;
#endif
#ifdef USE_BINARY_SENSOR
  std::vector<std::pair<size_t, binary_sensor::BinarySensor *>> binary_sensors_;
#endif
#ifdef USE_TEXT_SENSOR
  std::vector<std::pair<size_t, text_sensor::TextSensor *>> text_sensors_;
  text_sensor::TextSensor *bus_state_sensor_{nullptr};
#endif
#ifdef USE_NUMBER
  std::vector<std::pair<size_t, SpaNumber *>> numbers_;  // (field, entity), index = setpoint index
#endif
};

}  // namespace spa_bus
}  // namespace esphome
