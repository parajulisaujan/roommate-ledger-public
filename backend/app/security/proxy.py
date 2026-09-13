from ipaddress import ip_address, ip_network


def client_address(peer: str, forwarded: str, trusted_cidrs: str) -> str:
    """Walk from the socket peer toward the first untrusted hop; ignore spoofed prefixes."""
    networks = [ip_network(c.strip()) for c in trusted_cidrs.split(",") if c.strip()]
    if not networks or len(forwarded) > 2048:
        return peer
    try:
        current = ip_address(peer)
        hops = forwarded.split(",") if forwarded else []
        for hop in reversed(hops):
            if not any(current in network for network in networks):
                break
            current = ip_address(hop.strip())
        return str(current)
    except ValueError:
        return peer
