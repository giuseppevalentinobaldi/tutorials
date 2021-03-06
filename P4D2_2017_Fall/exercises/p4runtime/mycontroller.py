#!/usr/bin/env python2
import argparse
import os
from time import sleep

import p4runtime_lib.bmv2
import p4runtime_lib.helper

SWITCH_TO_HOST_PORT = 1
SWITCH_TO_SWITCH_PORT = 2

def writeTunnelRules(p4info_helper, ingressSw, egressSw, tunnelId, dstEthAddr, dstIpAddr):
    '''
    Installs three rules:
    1) An tunnel ingress rule on the ingress switch in the ipv4_lpm table that encapsulates traffic
       into a tunnel with the specified ID
    2) A transit rule on the ingress switch that forwards traffic based on the specified ID
    3) An tunnel egress rule on the egress switch that decapsulates traffic with the specified ID
       and sends it to the host

    :param p4info_helper: the P4Info helper
    :param ingressSw: the ingress switch connection
    :param egressSw: the egress switch connection
    :param tunnelId: the specified tunnel ID
    :param dstEthAddr: the destination IP to match in the ingress rule
    :param dstIpAddr: the destination Ethernet address to write in the egress rule
    '''
    # 1) Tunnel Ingress Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dstIpAddr, 32)
        },
        action_name="myTunnel_ingress",
        action_params={
            "dst_id": tunnelId,
        })
    ingressSw.WriteTableEntry(table_entry)
    print "Installed ingress tunnel rule on %s" % ingressSw.name

    # 2) Tunnel Transit Rule
    # TODO you will need to implement this rule
    # The rule will need to be added to the myTunnel_exact table and match on the tunnel ID (hdr.myTunnel.dst_id).
    # For our simple topology, transit traffic will need to be forwarded using the myTunnel_egress action to
    # the SWITCH_TO_SWITCH_PORT (port 2).
    # We will only need on transit rule on the ingress switch because we are using a simple topology.
    # In general, you'll need on transit rule for each switch in the path (except the last one)
    #
    # If you are stuck, start by copying the tunnel ingress rule from above. Then, try to make the suggested
    # modifications.
    print "TODO Install transit tunnel rule"

    # 3) Tunnel Egress Rule
    # For our simple topology, the host will always be located on the SWITCH_TO_HOST_PORT (port 1).
    # In general, you will need to keep track of which port the host is connected to.
    table_entry = p4info_helper.buildTableEntry(
        table_name="myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnelId
        },
        action_name="myTunnel_egress",
        action_params={
            "dstAddr": dstEthAddr,
            "port": SWITCH_TO_HOST_PORT
        })
    egressSw.WriteTableEntry(table_entry)
    print "Installed egress tunnel rule on %s" % egressSw.name

def readTableRules(p4info_helper, sw):
    '''
    Reads the table entries from all tables on the switch.

    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    '''
    print '\n----- Reading tables rules for %s -----' % sw.name
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            # TODO For extra credit, you can use the p4info_helper to translate the IDs the entry to names
            print entry
            print '-----'

def printCounter(p4info_helper, sw, counter_name, index):
    '''
    Reads the specified counter at the specified index from the switch. In our program, the index
    is the tunnel ID. If the index is 0, it will return all values from the counter.

    :param p4info_helper: the P4Info helper
    :param sw:  the switch connection
    :param counter_name: the name of the counter from the P4 program
    :param index: the counter index (in our case, the tunnel ID)
    '''
    for response in sw.ReadCounters(p4info_helper.get_counters_id(counter_name), index):
        for entity in response.entities:
            counter = entity.counter_entry
            print "%s %s %d: %d packets (%d bytes)" % (
                sw.name, counter_name, index,
                counter.data.packet_count, counter.data.byte_count
            )


def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4 Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    # Create a switch connection object for s1 and s2; this is backed by a P4 Runtime gRPC connection
    s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection('s1', address='127.0.0.1:50051')
    s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection('s2', address='127.0.0.1:50052')

    # Install the P4 program on the switches
    s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info, bmv2_json_file_path=bmv2_file_path)
    print "Installed P4 Program using SetForwardingPipelineConfig on %s" % s1.name
    s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info, bmv2_json_file_path=bmv2_file_path)
    print "Installed P4 Program using SetForwardingPipelineConfig on %s" % s2.name

    # Write the rules that tunnel traffic from h1 to h2
    writeTunnelRules(p4info_helper, ingressSw=s1, egressSw=s2, tunnelId=100,
                     dstEthAddr="00:00:00:00:02:02", dstIpAddr="10.0.2.2")

    # Write the rules that tunnel traffic from h2 to h1
    writeTunnelRules(p4info_helper, ingressSw=s2, egressSw=s1, tunnelId=200,
                     dstEthAddr="00:00:00:00:01:01", dstIpAddr="10.0.1.1")

    # TODO Uncomment the following two lines to read table entries from s1 and s2
    #readTableRules(p4info_helper, s1)
    #readTableRules(p4info_helper, s2)

    # Print the tunnel counters every 2 seconds
    try:
        while True:
            sleep(2)
            print '\n----- Reading tunnel counters -----'
            printCounter(p4info_helper, s1, "ingressTunnelCounter", 100)
            printCounter(p4info_helper, s2, "egressTunnelCounter", 100)
            printCounter(p4info_helper, s2, "ingressTunnelCounter", 200)
            printCounter(p4info_helper, s1, "egressTunnelCounter", 200)
    except KeyboardInterrupt:
        print " Shutting down."


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False, default='./build/advanced_tunnel.p4info')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False, default='./build/advanced_tunnel.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print "\np4info file not found: %s\nHave you run 'make'?" % args.p4info
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print "\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json
        parser.exit(1)

    main(args.p4info, args.bmv2_json)
