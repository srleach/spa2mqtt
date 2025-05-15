from spa2mqtt.spas.base.communicator import Communicator


class JacuzziEncryptedCommunicator(Communicator):
    """
    This is created for posterity. We don't currently envision any communication tier deviations for this behaviour.

    If you'd like to introduce your own Spa to this application, here is where you may lean on some of the plumbing -
    establishment of TCP connections, or perhaps even direct serial if you're so inclined.
    """
    pass
