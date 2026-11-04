// Host test driver for esphome/components/spa_bus/spa_protocol.cpp.
// Usage: replay <capture.log>   prints one line per changed field per status frame:
//   <status_frame_index> <field_index> <B|N|E|-> <value>
// plus self-checks of the codec and bus state machine (exit code != 0 on failure).
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "spa_protocol.h"

using namespace spa_proto;

#define CHECK(cond)                                                       \
  do {                                                                    \
    if (!(cond)) {                                                        \
      std::fprintf(stderr, "CHECK failed %s:%d: %s\n", __FILE__, __LINE__, #cond); \
      return 1;                                                           \
    }                                                                     \
  } while (0)

static void setup(SpaCore *core) {
#include "definition.inc"
}

static int self_checks() {
  // SpaControl example idle CC frame
  const uint8_t idle[] = {0x7E, 0x07, 0x10, 0xBF, 0xCC, 0x65, 0x85, 0xA6, 0x7E};
  CHECK(crc8(idle + 1, 6) == 0xA6);
  FrameDecoder dec;
  int got = 0;
  for (uint8_t b : idle) got += dec.push(b) ? 1 : 0;
  CHECK(got == 1 && dec.frame().type == 0xCC && cc_decode(dec.frame().payload, 2) == 0);
  uint8_t enc[2];
  cc_encode(0x04, 0x9F, enc);
  CHECK(cc_decode(enc, 2) == 0x04);
  uint8_t wire[80];
  Frame f;
  f.addr = 0x10;
  f.mid = 0xBF;
  f.type = 0xCC;
  f.payload_len = 2;
  f.payload[0] = 0x65;
  f.payload[1] = 0x85;
  CHECK(f.encode(wire) == 9 && std::memcmp(wire, idle, 9) == 0);

  // Bus: disabled -> nothing; enabled -> request on 0x00, ack on 0x02, CC on our CTS.
  BusClient bus;
  bus.config.command_type = 0xCC;
  CHECK(!bus.enqueue_press(0x04));
  bus.transmit_enabled = true;
  Frame cts, cc, newc, resp;
  cts.addr = 0x10; cts.mid = 0xBF; cts.type = 0x06;
  cc = f;
  newc.addr = 0xFE; newc.mid = 0xBF; newc.type = 0x00;
  for (int i = 0; i < 6; i++) {
    CHECK(bus.handle(cts).empty());
    CHECK(bus.handle(cc).empty());
  }
  CHECK(bus.state == BusState::LISTEN && bus.handle(newc).empty());  // lazy: no command, no claim
  CHECK(bus.enqueue_press(0x04) && bus.state == BusState::CLAIMING);
  auto out = bus.handle(newc);
  CHECK(out.size() == 1 && out[0].type == 0x01 && out[0].addr == 0xFE && out[0].payload_len == 3);
  resp.addr = 0xFE; resp.mid = 0xBF; resp.type = 0x02; resp.payload_len = 1; resp.payload[0] = 0x11;
  out = bus.handle(resp);
  CHECK(out.size() == 1 && out[0].type == 0x03 && out[0].addr == 0x11 && bus.state == BusState::READY);
  Frame ours = cts;
  ours.addr = 0x11;
  out = bus.handle(ours);
  CHECK(out.size() == 1 && out[0].type == 0xCC && cc_decode(out[0].payload, 2) == 0x04);

  // Setpoint controller: first press only enters set mode.
  SetpointController sp;
  sp.minimum = 20; sp.maximum = 40; sp.step = 0.5f; sp.confirm_frames = 3; sp.max_attempts = 10;
  CHECK(sp.set_target(39.2f) == 39.0f);
  CHECK(sp.on_status(true, 38.5f) == 0x01);   // wake press
  CHECK(sp.on_status(true, 38.5f) == -1);
  CHECK(sp.on_status(true, 38.5f) == -1);
  CHECK(sp.on_status(true, 38.5f) == 0x01);   // retry -> step
  CHECK(sp.on_status(true, 39.0f) == -1 && !sp.has_target);
  return 0;
}

int main(int argc, char **argv) {
  if (int rc = self_checks()) return rc;
  if (argc < 2) return 0;
  SpaCore core;
  setup(&core);
  std::ifstream in(argv[1]);
  std::string line;
  FrameDecoder dec;
  std::vector<Frame> tx;
  while (std::getline(in, line)) {
    const auto hash = line.find('#');
    if (hash != std::string::npos) line.resize(hash);
    std::istringstream ss(line);
    std::string ts, kind, hex;
    if (!(ss >> ts >> kind >> hex) || kind != "RX") continue;
    for (size_t i = 0; i + 1 < hex.size(); i += 2) {
      const uint8_t b = static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16));
      if (!dec.push(b)) continue;
      if (!core.on_frame(dec.frame(), tx)) continue;
      for (size_t k = 0; k < core.fields.size(); k++) {
        if (!core.changed[k]) continue;
        const FieldValue &v = core.values[k];
        std::printf("%u %zu ", core.status_frames, k);
        if (!v.valid) std::printf("- none\n");
        else if (v.kind == FieldKind::BOOL) std::printf("B %d\n", v.b ? 1 : 0);
        else if (v.kind == FieldKind::ENUM) std::printf("E %s\n", v.text->c_str());
        else std::printf("N %.6g\n", static_cast<double>(v.number));
      }
    }
  }
  if (!tx.empty()) {
    std::fprintf(stderr, "receive-only replay produced %zu frames to send\n", tx.size());
    return 3;
  }
  std::fprintf(stderr, "frames=%u crc_errors=%u status=%u\n", dec.stats.frames, dec.stats.crc_errors,
               core.status_frames);
  return 0;
}
