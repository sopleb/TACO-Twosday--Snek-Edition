#!/usr/bin/env python3
"""One-time converter: reads systemdata.bin (protobuf) and writes systemdata.json.

Usage:
    pip install protobuf
    python -m taco.tools.convert_systemdata

The protobuf schema is inferred from the C# [ProtoContract] classes:
  SolarSystemData { Id, NativeId, Name, X, Y, Z, ConnectedTo[] }
  SolarSystemConnectionData { ToSystemId, ToSystemNativeId, IsRegional }

The binary file is a length-delimited repeated message (protobuf-net serialises
arrays as repeated top-level messages with Serializer.Serialize<T[]>).
"""
import json
import struct
import sys
import os


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint, return (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, pos


def decode_message(data: bytes, pos: int, end: int) -> dict:
    """Decode protobuf fields from data[pos:end]."""
    fields = {}
    while pos < end:
        tag, pos = decode_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07

        if wire_type == 0:  # Varint
            value, pos = decode_varint(data, pos)
            fields[field_number] = value
        elif wire_type == 1:  # 64-bit
            value = struct.unpack_from('<d', data, pos)[0]
            pos += 8
            fields[field_number] = value
        elif wire_type == 2:  # Length-delimited
            length, pos = decode_varint(data, pos)
            value = data[pos:pos + length]
            pos += length
            if field_number not in fields:
                fields[field_number] = []
            if isinstance(fields[field_number], list):
                fields[field_number].append(value)
            else:
                fields[field_number] = [fields[field_number], value]
        elif wire_type == 5:  # 32-bit
            value = struct.unpack_from('<f', data, pos)[0]
            pos += 4
            fields[field_number] = value
        else:
            raise ValueError(f"Unknown wire type {wire_type} at pos {pos}")

    return fields


def decode_connection(data: bytes) -> dict:
    """Decode a SolarSystemConnectionData message."""
    fields = decode_message(data, 0, len(data))
    return {
        "to_system_id": fields.get(1, 0),
        "to_system_native_id": fields.get(2, 0),
        "is_regional": bool(fields.get(3, 0)),
    }


def decode_solar_system(data: bytes) -> dict:
    """Decode a SolarSystemData message."""
    fields = decode_message(data, 0, len(data))

    connections = []
    for conn_bytes in fields.get(7, []):
        connections.append(decode_connection(conn_bytes))

    name_parts = fields.get(3, [])
    if isinstance(name_parts, list) and name_parts:
        name = name_parts[0].decode('utf-8')
    elif isinstance(name_parts, bytes):
        name = name_parts.decode('utf-8')
    else:
        name = ""

    return {
        "id": fields.get(1, 0),
        "native_id": fields.get(2, 0),
        "name": name,
        "x": fields.get(4, 0.0),
        "y": fields.get(5, 0.0),
        "z": fields.get(6, 0.0),
        "connected_to": connections,
    }


def convert(input_path: str, output_path: str):
    """Convert protobuf binary to JSON."""
    with open(input_path, 'rb') as f:
        data = f.read()

    systems = []
    pos = 0
    while pos < len(data):
        # protobuf-net writes each array element as a length-delimited field
        # with field number 1, wire type 2
        tag, pos = decode_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07

        if wire_type != 2:
            raise ValueError(f"Expected wire type 2, got {wire_type} at pos {pos}")

        length, pos = decode_varint(data, pos)
        msg_data = data[pos:pos + length]
        pos += length

        system = decode_solar_system(msg_data)
        systems.append(system)

    with open(output_path, 'w') as f:
        json.dump(systems, f, indent=1)

    print(f"Converted {len(systems)} systems to {output_path}")
    return systems


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.join(script_dir, "..", "resources", "data", "systemdata.bin")
    default_output = os.path.join(script_dir, "..", "resources", "data", "systemdata.json")

    input_path = sys.argv[1] if len(sys.argv) > 1 else default_input
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_output

    convert(input_path, output_path)
