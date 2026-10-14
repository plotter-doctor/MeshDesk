"""Descriptor-driven settings: new upstream protobuf fields appear automatically."""
import base64
import json
import math
import re
import ipaddress
from functools import lru_cache
from pathlib import Path
from google.protobuf import json_format, message_factory
from google.protobuf.descriptor import FieldDescriptor as F
from meshtastic.protobuf import config_pb2, module_config_pb2, mesh_pb2, channel_pb2


def to_dict(message, defaults=False):
    return json_format.MessageToDict(message, preserving_proto_field_name=True,
                                    always_print_fields_with_no_presence=defaults)


def safe_data(value):
    if hasattr(value, "DESCRIPTOR"):
        return safe_data(to_dict(value))
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, dict):
        return {str(k): safe_data(v) for k, v in value.items()
                if k not in ("raw", "adminSessionPassKey", "session_passkey", "sessionPasskey")}
    if isinstance(value, (tuple, list)):
        return [safe_data(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def label(name):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").capitalize()


def sections():
    out = [{"key": "user", "title": "Owner", "group": "Device"}]
    for group, cls in [("Radio / device", config_pb2.Config), ("Modules", module_config_pb2.ModuleConfig)]:
        for field in cls.DESCRIPTOR.fields:
            if field.message_type and field.name != 'sessionkey':
                out.append({"key": ("config." if group != "Modules" else "module.") + field.name,
                            "title": label(field.name), "group": group})
    for i in range(8):
        out.append({"key": f"channel.{i}", "title": f"Channel {i}", "group": "Channels"})
    return out


def new_message(section):
    if section == "user":
        return mesh_pb2.User()
    group, name = section.split(".", 1)
    if group == "channel":
        if not 0 <= int(name) < 8:
            raise ValueError("Channel must be between 0 and 7")
        return channel_pb2.Channel(index=int(name))
    cls = {"config": config_pb2.Config, "module": module_config_pb2.ModuleConfig}[group]
    descriptor = cls.DESCRIPTOR.fields_by_name[name].message_type
    return message_factory.GetMessageClass(descriptor)()


def fields(message, prefix=""):
    result = []
    for f in message.DESCRIPTOR.fields:
        path = prefix + f.name
        value = getattr(message, f.name)
        row = {"path": path, "title": label(f.name), "secret": bool(re.search(r'password|psk|private_key|admin_key', path)),
               "help": f.full_name, "choices": [], "kind": "text"}
        if f.is_repeated:
            row.update(kind="json", value=json.dumps(to_dict(message, True).get(f.name, [])))
        elif f.type == F.TYPE_MESSAGE:
            result.extend(fields(value, path + "."))
            continue
        elif f.type == F.TYPE_ENUM:
            row.update(kind="enum", value=int(value), choices=[{"label": x.name, "value": x.number} for x in f.enum_type.values])
        elif f.type == F.TYPE_BOOL:
            row.update(kind="bool", value=bool(value))
        elif f.type == F.TYPE_BYTES:
            row.update(kind="bytes", value=base64.b64encode(value).decode(), help=f.full_name + " — base64")
        elif '.IpV4Config.' in f.full_name:
            row.update(kind='ip',value=str(ipaddress.IPv4Address(int(value).to_bytes(4,'little'))))
        elif f.type in (F.TYPE_FLOAT, F.TYPE_DOUBLE):
            row.update(kind="number", value=str(value))
        elif f.type == F.TYPE_STRING:
            row["value"] = value
        else:
            row.update(kind="integer", value=str(value))
        result.append(row)
    return result


def set_field(message, path, value):
    if path.startswith('admin_key.'):
        index=int(path.split('.')[1])
        if not 0<=index<3:raise ValueError('At most three admin keys are supported')
        key=base64.b64decode(value,validate=True)
        if len(key) not in (0,32):raise ValueError('An admin public key must contain 32 bytes')
        while len(message.admin_key)<=index:message.admin_key.append(b'')
        message.admin_key[index]=key
        while message.admin_key and not message.admin_key[-1]:del message.admin_key[-1]
        return
    parts = path.split(".")
    obj = message
    for part in parts[:-1]:
        obj = getattr(obj, part)
    f = obj.DESCRIPTOR.fields_by_name[parts[-1]]
    if f.is_repeated:
        parsed = json.loads(value) if isinstance(value, str) else value
        patch = type(obj)()
        json_format.ParseDict({f.name: parsed}, patch)
        obj.ClearField(f.name)
        obj.MergeFrom(patch)
        return
    if f.type == F.TYPE_BYTES:
        value = base64.b64decode(value, validate=True)
    elif f.type == F.TYPE_BOOL:
        if not isinstance(value, bool):
            if str(value).lower() not in ("true", "false"):
                raise ValueError("Expected true or false")
            value = str(value).lower() == "true"
    elif f.type == F.TYPE_ENUM:
        value = int(value)
        if value not in f.enum_type.values_by_number:
            raise ValueError("Unknown enum value")
    elif '.IpV4Config.' in f.full_name and isinstance(value,str) and '.' in value:
        value=int.from_bytes(ipaddress.IPv4Address(value).packed,'little')
    elif f.type in (F.TYPE_FLOAT, F.TYPE_DOUBLE):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Number must be finite")
    elif f.type != F.TYPE_STRING:
        value = int(value)
    setattr(obj, f.name, value)


@lru_cache(maxsize=1)
def validation_rules():
    return json.loads((Path(__file__).parent/'resources/web-validation.json').read_text())


def validate_section(section, message):
    from .forms import metadata,disabled,value_at
    controls={f['path']:f for f in metadata().get(section,[])}
    for path,rule in validation_rules().get(section,{}).items():
        if path in controls and disabled(message,controls[path]):continue
        value=value_at(message,path)
        value=len(value) if rule['kind']=='string' else value
        if rule.get('integer') and value!=int(value):raise ValueError(label(path)+' must be a whole number')
        if 'min' in rule and value<rule['min']:raise ValueError(label(path)+f" must be at least {rule['min']:g}")
        if 'max' in rule and value>rule['max']:raise ValueError(label(path)+f" must be at most {rule['max']:g}"+(' characters' if rule['kind']=='string' else ''))
    if section == "user":
        if not message.long_name.strip() or not message.short_name.strip():
            raise ValueError("Owner names cannot be empty")
        if len(message.long_name.encode()) > 39 or len(message.short_name.encode()) > 4:
            raise ValueError("Owner names must fit 39 bytes (long) and 4 bytes (short)")
    if section.startswith("channel."):
        if message.index!=int(section.split('.')[1]):
            raise ValueError('A channel draft cannot change its channel index')
        if message.index == 0 and message.role != channel_pb2.Channel.PRIMARY:
            raise ValueError("Channel 0 must remain primary")
        if message.index != 0 and message.role == channel_pb2.Channel.PRIMARY:
            raise ValueError("Only channel 0 may be primary")
        if len(message.settings.name.encode()) > 11:
            raise ValueError("Channel name must fit 11 UTF-8 bytes")
        if len(message.settings.psk) not in (0, 1, 16, 32):
            raise ValueError("Channel key must contain 0, 1, 16 or 32 bytes")
    if section == "config.lora" and message.hop_limit > 7:
        raise ValueError("Hop limit must be between 0 and 7")
    if section == 'config.lora' and message.override_frequency and not 410<=message.override_frequency<=930:
        raise ValueError('Override frequency must be 0 or between 410 and 930 MHz')
    if section == "config.security":
        if len(message.private_key) not in (0, 32) or len(message.public_key) not in (0, 32):
            raise ValueError("Identity keys must contain 32 bytes")
        if len(message.admin_key)>3 or any(len(k) not in (0,32) for k in message.admin_key):
            raise ValueError('Use at most three 32-byte admin public keys')
        if message.is_managed and not any(message.admin_key):
            raise ValueError('Managed mode requires an admin public key')
