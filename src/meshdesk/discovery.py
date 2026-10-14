"""Non-invasive serial discovery; a USB bridge is not proof of its firmware."""


def serial_devices(ports,known=()):
    from meshtastic.util import whitelistVids
    # Common bridges/USB controllers used by supported Meshtastic boards.
    candidates=set(whitelistVids)|{0x10c4,0x1a86,0x0403,0x2e8a,0x1915}
    result=[]
    for port in ports:
        description=port.description or port.device
        vid=getattr(port,'vid',None)
        advertised=any(word in description.lower() for word in ('meshtastic','heltec','lilygo','rakwireless','wisblock','t-echo','t-beam'))
        verified=port.device in known
        likely=verified or advertised or vid in candidates
        result.append({'name':description,'address':port.device,'likely':likely,'verified':verified,
                       'hint':'Previously connected Meshtastic radio' if verified else 'Compatible USB device · not verified' if likely else 'Other serial port'})
    return sorted(result,key=lambda d:(not d['verified'],not d['likely'],d['address']))
