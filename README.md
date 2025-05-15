# spa2mqtt
An experimental tool building upon community research to control Jacuzzi spas via the exposed RS485 headers on the 
main control board.
 
Builds upon SundanceRS485 as linked below from HyperactiveJ and those inspiring that work too.

## Concepts:
- Prior implementations are tightly coupled to a board type (as currently is this)
- Many concepts remain the same regardless of whether we're using Jacuzzi, Sundance, Balboa and potentially others
- We'd ideally like to restrict required config on a well configured HA instance to as low as possible
- The aim is to move all logic into dependencies where possible, and behaviours into config files
  - The real aim is that new tubs & board types can be added simply, and users can simply set a tub type in an env var
  - Perhaps we could even autodiscover this if a tub responds to identification packets 
- There will be some support at the code level required for changes such as "encryption" found on some panels

## Connectivity
TBC: RS485 -> Wi-Fi adapter
Include wiring example

## Detecting Config
Temp scale (aka units) may be represented in the status update on data[14] 

> It does not currently appear to be in 14 or 18. Further research required.

```python
if i == 14:
    self.log.info(f"TS: {data[i] & 0x01}") # 1 = tscale_c else tscale_f
```

## Sending Control Commands
TBC
- Representation of current state vs commanded state
- Queue loop to update parameters to bring current to commanded position
  - How to handle changes on the control panel while this is underway?

## Supported Hot Tubs / Boards

### Jacuzzi

| Model | Year | Board | Encrypted | Comms Device | Supports | Wiring       |
|-------|------|-------|-----------|--------------|----------|--------------|
| J235  | 2018 |       | Yes       | EW11A        | TBC      | 12v +/, A/B  |

## TODO
- Clean up sundanceRS485.py and reduce the unnecessary/debugging code that isn't called or used
- Map out values of interest that we don't currently have valid results for
  - Filter Life
  - Water Life
  - ClearRay Life
  - Flow sensor?
  - 2nd Thermistor?

## Credits & Sources
- https://github.com/HyperActiveJ/SundanceJacuzzi_HomeAssistant_TCP_RS485
  - Initial Working Code
  - https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp/issues/1 for similar hardware
