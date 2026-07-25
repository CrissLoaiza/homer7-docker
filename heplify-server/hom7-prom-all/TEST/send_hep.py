#!/usr/bin/env python3
import socket, struct, sys, time, json

def chunk(vendor, ctype, body):
    hdr = struct.pack("!HHH", vendor, ctype, 6 + len(body))
    return hdr + body

def build_hep(proto_type, src_ip, dst_ip, src_port, dst_port, node_id, payload, cid=None):
    chunks = b""
    chunks += chunk(0, 1, bytes([2]))               # Version = IPv4
    chunks += chunk(0, 2, bytes([0x11]))             # Protocol = UDP
    chunks += chunk(0, 3, socket.inet_aton(src_ip))  # IP4SrcIP
    chunks += chunk(0, 4, socket.inet_aton(dst_ip))  # IP4DstIP
    chunks += chunk(0, 7, struct.pack("!H", src_port))  # SrcPort
    chunks += chunk(0, 8, struct.pack("!H", dst_port))  # DstPort
    now = time.time()
    chunks += chunk(0, 9, struct.pack("!I", int(now)))                 # Tsec
    chunks += chunk(0, 10, struct.pack("!I", int((now % 1) * 1e6)))    # Tmsec
    chunks += chunk(0, 11, bytes([proto_type]))      # ProtoType
    chunks += chunk(0, 12, struct.pack("!I", node_id))  # NodeID
    if cid:
        chunks += chunk(0, 17, cid.encode())          # CID
    payload_b = payload.encode() if isinstance(payload, str) else payload
    chunks += chunk(0, 15, payload_b)                 # Payload

    total_len = 6 + len(chunks)
    header = b"HEP3" + struct.pack("!H", total_len)
    return header + chunks

def send(dst_addr, dst_port_udp, packet):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(packet, (dst_addr, dst_port_udp))
    s.close()

if __name__ == "__main__":
    mode = sys.argv[1]
    target_host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    target_port = int(sys.argv[3]) if len(sys.argv) > 3 else 9060

    if mode == "horaclifix":
        payload = json.dumps({
            "NAME": "sbc-test-1",
            "INC_REALM": "access",
            "OUT_REALM": "core",
            "INC_MOS": 420, "INC_RVAL": 8500, "INC_RTP_PK": 5000, "INC_RTP_PK_LOSS": 12,
            "INC_RTP_AVG_JITTER": 8, "INC_RTP_MAX_JITTER": 22,
            "INC_RTCP_PK": 50, "INC_RTCP_PK_LOSS": 1, "INC_RTCP_AVG_JITTER": 6, "INC_RTCP_MAX_JITTER": 15,
            "INC_RTCP_AVG_LAT": 30, "INC_RTCP_MAX_LAT": 45,
            "OUT_MOS": 410, "OUT_RVAL": 8300, "OUT_RTP_PK": 5000, "OUT_RTP_PK_LOSS": 18,
            "OUT_RTP_AVG_JITTER": 9, "OUT_RTP_MAX_JITTER": 25,
            "OUT_RTCP_PK": 50, "OUT_RTCP_PK_LOSS": 2, "OUT_RTCP_AVG_JITTER": 7, "OUT_RTCP_MAX_JITTER": 18,
            "OUT_RTCP_AVG_LAT": 32, "OUT_RTCP_MAX_LAT": 48,
        })
        pkt = build_hep(38, "192.168.1.185", "192.168.1.185", 5062, 5063, 2002, payload)
        send(target_host, target_port, pkt)
        print("sent horaclifix HEP, bytes=", len(pkt))

    elif mode == "rtcp":
        payload = json.dumps({
            "report_blocks": [{
                "fraction_lost": 40,
                "packets_lost": 25,
                "ia_jitter": 35,
                "dlsr": 500,
            }],
            "report_blocks_xr": {
                "fraction_lost": 0, "fraction_discard": 0, "burst_density": 0,
                "gap_density": 0, "burst_duration": 0, "gap_duration": 0,
                "round_trip_delay": 0, "end_system_delay": 0,
            },
            "ssrc": 123456789, "type": 201, "report_count": 1,
        })
        pkt = build_hep(5, "192.168.1.185", "192.168.1.185", 16000, 17000, 2002, payload, cid="synthetic-bad-call-1")
        send(target_host, target_port, pkt)
        print("sent bad-qos rtcp HEP, bytes=", len(pkt))
    else:
        print("usage: send_hep.py [horaclifix|rtcp] [host] [port]")
        sys.exit(1)
