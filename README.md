# spa2mqtt
An experimental tool building upon community research to control Jacuzzi spas via the exposed RS485 headers on the 
main control board.

This is opinionated. It assumes you're using MQTT and ultimately consuming this from within home assistant. 

# Warning: 
This works for my use case, and I'm making a good faith attempt at trying to get something that works for many. 
I can't take responsibility for any damage this may cause, or that you may cause when wiring things in. Anything really!
A spa contains high voltage, and likely a huge potential fault current so exercise incredible caution when doing 
anything within it.
 
Builds upon SundanceRS485 as linked below from HyperactiveJ and those inspiring that work too.

## Usage

1. Create a config.yml in the repository root: `cp config.yml.example config.yml`
2. Update the variables required in the config to get connected to your tub and MQTT.
   3. You'll need to ensure you've set up the IP address and port of the tub's RS485 converter. If you're using the 
      EW11A then your port is likely to be 8899, if you're using the prolink, I believe you can still connect 
      but I haven't got one to test.
3. docker-compose run -d .

## Issues
If it doesn't work for your tub, i'd encourage you to open an issue with info. I'd love to make this work for a range
of hardware, and if you're happy to assist by providing raw data packets from the tub, I'm happy to make an effort to 
try and get it to work within this framework.

Of course, if you're able - I also welcome you to join in and contribute. I am not a Python developer by trade, and many
of my architectural and implementation details are biased by other languages and patterns, and I am open to any positive
change or suggestions.

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

## Upstream 
As above, the solution is opinionated. It assumes you're using MQTT to feed home assistant and as a result some 
assumptions are made. If there's demand, I've left the MQTT/HA specifics at arms length from the actual spa comms side
of things, and we can always work to decouple this if the community so desires.

## Detecting Config
TBC

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
- Map out values of interest that we don't currently have valid results for
  - Filter Life
  - Water Life
  - ClearRay Life
  - Flow sensor?
  - 2nd Thermistor?
- Find an appropriate way to implement a control loop for input that requires us to hit a number of buttons. 
- Find a way to directly control the temperature if at all possible. This may need someone with a prolink and an EW11A 
to sniff the bus traffic. Open an issue if this describes you!

## Credits, Inspiration & Sources
- https://github.com/HyperActiveJ/SundanceJacuzzi_HomeAssistant_TCP_RS485 Initial Working Code & inspiration to build upon it
- https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp/issues/1 for similar hardware
- https://github.com/garbled1/pybalboa for some of the minutiae around comms with the tub itself
- https://github.com/ccutrer/balboa_worldwide_app for more of the above
- https://github.com/jackbrown1993/Jacuzzi-RS485 for his building upon the work also listed above