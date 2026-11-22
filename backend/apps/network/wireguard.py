"""A WireGuard configuration as wg-quick writes it and VPN providers hand it out, read into what
the service `tunnel` runs. Keys only wg-quick acts on (Table, PostUp, SaveConfig…) and DNS search
domains bear on no route there and are left out."""

import base64
import binascii
import ipaddress


class Invalid(ValueError):
    pass


def _key(value: str, name: str) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        raw = b""
    if len(raw) != 32:
        raise Invalid(f"{name} is not a WireGuard key")
    return value


def _sections(text: str) -> list[tuple[str, dict[str, list[str]]]]:
    sections: list[tuple[str, dict[str, list[str]]]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            sections.append((line[1:-1].strip().lower(), {}))
            continue
        name, equals, value = line.partition("=")
        if not equals or not sections:
            raise Invalid(f"line {number} is neither a section nor a setting")
        sections[-1][1].setdefault(name.strip().lower(), []).append(value.strip())
    return sections


def _listed(values: dict[str, list[str]], name: str) -> list[str]:
    return [
        each.strip() for value in values.get(name, []) for each in value.split(",") if each.strip()
    ]


def _one(values: dict[str, list[str]], name: str, section: str) -> str:
    found = values.get(name, [])
    if len(found) != 1 or not found[0]:
        raise Invalid(f"[{section}] needs one {name}")
    return found[0]


def _prefix(value: str) -> str:
    try:
        return str(ipaddress.ip_interface(value))
    except ValueError:
        raise Invalid(f"{value} is not an address") from None


def _network(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError:
        raise Invalid(f"{value} is not a network") from None


def _endpoint(value: str) -> str:
    host, colon, port = value.rpartition(":")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not colon or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise Invalid(f"{value} is not an endpoint (host:port)")
    return value


def _number(values: dict[str, list[str]], name: str, section: str, top: int) -> int:
    found = values.get(name)
    if not found:
        return 0
    if len(found) != 1 or not found[0].isdigit() or not 0 < int(found[0]) <= top:
        raise Invalid(f"[{section}] {name} is not a number up to {top}")
    return int(found[0])


def parsed(text: str) -> dict:
    """The configuration as the service runs it; Invalid where it cannot be."""
    sections = _sections(text)
    interfaces = [values for section, values in sections if section == "interface"]
    if len(interfaces) != 1:
        raise Invalid("the configuration needs one [Interface]")
    interface = interfaces[0]
    addresses = [_prefix(each) for each in _listed(interface, "address")]
    if not addresses:
        raise Invalid("[Interface] needs an Address")
    dns = []
    for each in _listed(interface, "dns"):
        try:
            dns.append(str(ipaddress.ip_address(each)))
        except ValueError:
            pass
    peers = []
    for section, values in sections:
        if section != "peer":
            continue
        shared = values.get("presharedkey")
        peers.append(
            {
                "public_key": _key(_one(values, "publickey", "Peer"), "PublicKey"),
                "preshared_key": _key(shared[0], "PresharedKey") if shared else "",
                "endpoint": _endpoint(_one(values, "endpoint", "Peer")),
                "allowed_ips": [_network(each) for each in _listed(values, "allowedips")],
                "keepalive": _number(values, "persistentkeepalive", "Peer", 65535),
            }
        )
    if not peers:
        raise Invalid("the configuration needs a [Peer]")
    return {
        "private_key": _key(_one(interface, "privatekey", "Interface"), "PrivateKey"),
        "addresses": addresses,
        "dns": dns,
        "mtu": _number(interface, "mtu", "Interface", 9000),
        "peers": peers,
    }


def shown(spec: dict) -> dict:
    """What the settings show of a configuration, nothing that lets anyone in."""
    return {
        "address": spec["addresses"][0].split("/")[0],
        "endpoint": ", ".join(peer["endpoint"] for peer in spec["peers"]),
    }
