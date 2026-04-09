from scapy.all import sniff

def packet_callback(packet):
    print("\n=== Packet Captured ===")

    if packet.haslayer("IP"):
        print("Source IP:", packet["IP"].src)
        print("Destination IP:", packet["IP"].dst)

    if packet.haslayer("TCP"):
        print("Source Port:", packet["TCP"].sport)
        print("Destination Port:", packet["TCP"].dport)

    if packet.haslayer("Raw"):
        try:
            payload = packet["Raw"].load
            print("Payload:", payload.decode(errors="ignore"))
        except:
            print("Payload: (binary data)")

# Capture packets
sniff(iface="h3-eth0", prn=packet_callback, store=False)