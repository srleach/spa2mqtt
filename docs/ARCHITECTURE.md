# Architecture

## Overview

spa2mqtt is designed to connect to various hot tub spa control boards via TCP/RS485 and publish their state to MQTT for Home Assistant consumption.

## Core Concepts

### 1. Protocol Layer (`spa2mqtt/protocols/`)

Different spa manufacturers use different communication protocols. The protocol layer abstracts these differences:

- `Protocol` - Abstract base class defining the interface
- `PlaintextProtocol` - For unencrypted spa communication
- `JacuzziEncryptedProtocol` - For Jacuzzi J235 encrypted communication

Each protocol handles:
- Packet marker (delimiter byte, usually 0x7E)
- Packet type enum (for decoding message types)
- Body decoding (e.g., XOR for encrypted protocols)

### 2. Transport Layer (`spa2mqtt/spas/base/communicator/`)

Handles the actual TCP connection to the spa's RS485-to-WiFi adapter:

- `Communicator` - Base TCP client
- `SimulatedCommunicator` - For testing with captured data

### 3. Spa Layer (`spa2mqtt/spas/`)

Contains spa-specific implementations:

- `base/spa/spa.py` - Generic spa class with protocol support
- `jacuzzi_encrypted/spa/jacuzzi_encrypted_spa.py` - J235-specific logic (channel claiming, commands)

### 4. Message Layer (`spa2mqtt/spas/base/messages/`)

Converts raw packets to usable state:

- `Message` - Base class with field decoding
- `MessageFactory` - Creates appropriate message type from packet

### 5. Configuration (`spa2mqtt/spa_definitions/`)

YAML files define:
- Which protocol to use
- Which message fields to decode
- MQTT entity mappings for Home Assistant

## Adding a New Spa Type

1. **Create protocol** (if new):
   - Add to `spa2mqtt/protocols/`
   - Implement `Protocol` interface

2. **Create spa definition**:
   - Add YAML file to `spa2mqtt/spa_definitions/`
   - Specify `family`, `communicator`, `spa`, `message_configuration`

3. **Create spa class** (if custom logic needed):
   - Extend base `Spa` class
   - Override `process_update()` for custom handling

## Data Flow

```
TCP Stream → Communicator → Packet → Protocol.decode_body() 
           → MessageFactory → Message → decode_params() 
           → MQTT → Home Assistant
```