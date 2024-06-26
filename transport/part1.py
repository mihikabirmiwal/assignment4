##
## Python version of:
##
## ****************************************************************************
## ALTERNATING BIT AND GO-BACK-N NETWORK SIMULATOR: VERSION 1.1  J.F.Kurose
##
## Network properties/assumptions:
##   - one-way network delay averages 5.0 time units (longer if there
##     are other messages in the channel for GBN), but can be larger
##   - packets can be corrupted (either the header or the data portion)
##     or lost, according to user-defined probabilities
##   - packets will be delivered in the order in which they were sent
##     (although some can be lost).
## ****************************************************************************
##
## Modified by:
## Jeongyoon Moon <jeongyoonm@utexas.edu>
## University of Texas at Austin
## March 2024
##
## Python version by:
## Eric Eide <eeide@cs.utah.edu>
## University of Utah
## March 2022
##
## Run `python3 <thisfile.py> -h` in a terminal window to see the various
## parameters that you can set for a run of this simulator.
##
## This program defines a variable `TRACE` that you can use to conditionally
## print messages from your SndTransport and RcvTransport methods.  For example:
##
##   if TRACE>0:
##       print('A very important event just happened!')
##
## The value of `TRACE` is set by the `-v` command line option.  The default
## value of `TRACE` is 0 (meaning "no tracing").
##

import argparse
from copy import deepcopy
from enum import Enum, auto
import random
import sys
import time
import transport.init_sim as sim

###############################################################################

## ************************* BASIC DATA STRUCTURES ****************************
##
## STUDENTS: Do not modify these definitions.
##
## ****************************************************************************

# A Msg is the data unit passed from layer 5 (done by the provided code) 
# to layer 4 (your code).  It contains the data (bytes) to be delivered to layer 5
# via your transport-level protocol entities.

class Msg:
    MSG_SIZE = 20

    def __init__(self, data):
        self.data = data                # type: bytes[MSG_SIZE]

    def __str__(self):
        return 'Msg(data=%s)' % (self.data)

# A Pkt is the data unit passed from layer 4 (your code) to layer 3
# (handled by the provided code). Note the pre-defined packet structure, 
# which you must follow.

class Pkt:
    def __init__(self, seqnum:int, acknum:int, checksum:int, payload:bytes):
        self.seqnum = seqnum            # type: integer
        self.acknum = acknum            # type: integer
        self.checksum = checksum        # type: integer
        self.payload = payload          # type: bytes[Msg.MSG_SIZE]

    def __str__(self):
        return ('Pkt(seqnum=%s, acknum=%s, checksum=%s, payload=%s)'
                % (self.seqnum, self.acknum, self.checksum, self.payload))

###############################################################################

## ***************** TASKS: COMPLETE THE CODE BELOW **************************
##
## The code blocks you have to implement are marked as TODO
##
## NOTICE: When you implement these methods, use instance variables only!
## I.e., variables that you access through `self' like `self.x`.  Do NOT use
## global variables (a.k.a. module-scoped variables) or class variables.
##
## The reason for this restriction is the autograder, which may run several
## simulations within a single Python process.  For each simulation, the
## autograder will create a new instance of SndTransport and a new instance of
## RcvTransport.  If you use global variables and/or class variables in your
## implmentations of SndTransport and RcvTransport, then your code may not work properly
## when run by the autograder, and you may LOSE POINTS!
## ****************************************************************************

def append_ints(num1: int, num2: int):
    return (num1 << 8) | num2

# TODONE: Write a function that calculates a checksum given a packet.
def calc_checksum(pkt:Pkt):
    sum = 0
    # handle seqnum and acknum
    sum += append_ints(pkt.seqnum, pkt.acknum)
    if sum & 0xFFFF0000:
        sum &= 0xFFFF
        sum += 1

    # handle payload
    count = len(pkt.payload)/2
    index = 0
    while index < count:
        sum += pkt.payload[index]
        index += 1
        if sum & 0xFFFF0000:
            sum &= 0xFFFF
            sum += 1
    return ~(sum & 0xFFFF)

# SndTransport: a sender transport layer (layer 4)
class SndTransport:
    # The following method will be called once (only) before any other
    # SndTransport methods are called.  You can use it to do any initialization.
    #
    # seqnum_limit is "the number of distinct seqnum values that your protocol
    # may use."  The seqnums and acknums in all layer3 Pkts must be between
    # zero and seqnum_limit-1, inclusive.  E.g., if seqnum_limit is 16, then
    # all seqnums must be in the range 0-15.
    def __init__(self, seqnum_limit, timeout_val=40, window_size=2):
        self.window_size = window_size
        self.seqnum_limit = seqnum_limit
        self.last_ack_rec = -1
        self.next_frame_index = 0
        self.unackPkt = []
        self.timeout_val = timeout_val
    
    # increment next frame index, wraps around seqnum_limit
    def inc_nfi(self):
        if self.next_frame_index < self.seqnum_limit - 1:
            self.next_frame_index += 1
        else:
            self.next_frame_index = 0

    # return incremented last ack received, wraps around seqnum_limit
    def next_lar(self):
        if self.last_ack_rec < self.seqnum_limit - 1:
            return self.last_ack_rec + 1
        else:
            return 0

    # can send more packets if there are more slots in window_size available
    def check_send(self):
        return len(self.unackPkt) < self.window_size
        
    # Called from layer 5, passed the data to be sent to other side.
    # The argument `message` is a Msg containing the data to be sent.
    def send(self, message):
        # TODONE: Create a packet from the message and pass it to layer 3. 
        # This method also has to check # of in-flight packets and 
        # start a timer after sending the packet.
        # Refer to the assignment webpage for the core logic.

        # if space to send more in window, send packet. if not, drop
        if self.check_send():
            pkt = Pkt(self.next_frame_index, self.next_frame_index, 0, message.data)
            pkt.checksum = calc_checksum(pkt)
            self.inc_nfi()
            self.unackPkt.append(pkt)
            to_layer3(self, pkt)
            start_timer(self, self.timeout_val)
        else:
            print("error: unacknowledged packets, max number of packets still in flight")

    # retransmit all unacked packets 
    def retransmit(self):
        if len(self.unackPkt) > 0:
            for packet in self.unackPkt:
                to_layer3(self, packet)
            start_timer(self, self.timeout_val)

    # checking validity of an ACK/NACK packet it is receiving
    def check_rec(self, pkt):       
        return pkt.acknum == pkt.seqnum and pkt.checksum == calc_checksum(pkt)

    # Called from layer 3, when a packet arrives for layer 4 at SndTransport.
    # The argument `packet` is a Pkt containing the newly arrived packet.
    def recv(self, pkt):
        # TODONE: Check the packet if it is corrupted or unexpected
        # and pass/discard the packet to layer 5 based on them.
        # Refer to the assignment webpage for the core logic.

        stop_timer(self)
        if self.check_rec(pkt):
            if pkt.seqnum == self.next_lar():
                self.last_ack_rec = self.next_lar()
                self.unackPkt.pop(0)
                to_layer5(self, Msg(pkt.payload))
            elif pkt.seqnum > self.next_lar():
                self.retransmit()
        else:
            self.retransmit()
            

    # Called when the sender's timer goes off.
    def timer_interrupt(self):
        # TODONE: handle retransmission when the timer expires
        self.retransmit()


# RcvTransport: a receiver transport layer (layer 4)
class RcvTransport:
    # The following method will be called once (only) before any other
    # RcvTransport methods are called.  You can use it to do any initialization.
    #
    # See comment above `SndTransport.__init__` for the meaning of seqnum_limit.
    def __init__(self, seqnum_limit):
        # TODONE: initalize the receiver's states
        self.seqnum_limit = seqnum_limit
        self.last_frame_rec = -1

    # returns the next frame we expect, wrap around seqnum_limit
    def next_frame_rec(self):
        if self.last_frame_rec < self.seqnum_limit - 1:
            return self.last_frame_rec + 1
        else:
            return 0
    
    def check_rec(self, packet):
        return calc_checksum(packet) == packet.checksum
        

    # Called from layer 3, when a packet arrives for layer 4 at RcvTransport.
    # The argument `packet` is a Pkt containing the newly arrived packet.
    def recv(self, packet):
        # TODONE: Check the packet if it is corrupted or unexpected
        # and pass/discard the packet to layer 5 based on them.
        # Plus, send an ACK message based on the validity of the packet.
        # Refer to the assignment webpage for the core logic.
        if self.check_rec(packet): 
            if packet.seqnum == self.next_frame_rec():
                to_layer5(self, Msg(packet.payload))
                self.last_frame_rec = self.next_frame_rec()
            ack = Pkt(packet.seqnum, packet.seqnum, 0, packet.payload)
            ack.checksum = calc_checksum(ack)
            to_layer3(self, ack)
        else:
            fraud_ack_num = packet.seqnum - 1
            if packet.seqnum == 0:
                fraud_ack_num = 1
            nack = Pkt(packet.seqnum, fraud_ack_num, 0, packet.payload)
            nack.checksum = calc_checksum(nack)
            to_layer3(self, nack)
        
    # Ignore this method!
    def timer_interrupt(self):
        pass

###############################################################################

## ********************** STUDENT-CALLABLE FUNCTIONS **************************
##
## NOTICE: These are functions that should be called from your SndTransport and
## RcvTransport methods.
##
## The first argument to each of these student-callable functions is the object
## that is invoking the function.  Within an SndTransport or RcvTransport method, that
## object is available as `self`.  For example, to start a timer in one of your
## entity methods, you would do something like:
##
##   start_timer(self, 10.0) # Start a timer that will go off in 10 time units.
##
## Or to send a packet to layer3, you would do something like:
##
##   to_layer3(self, Pkt(...)) # Construct a Pkt and send it to layer3.
##
## ****************************************************************************

def start_timer(calling_entity, increment):
    sim.the_sim.start_timer(calling_entity, increment)

def stop_timer(calling_entity):
    sim.the_sim.stop_timer(calling_entity)

def to_layer3(calling_entity, packet):
    sim.the_sim.to_layer3(calling_entity, packet)

def to_layer5(calling_entity, message):
    sim.the_sim.to_layer5(calling_entity, message)

def get_time(calling_entity):
    return sim.the_sim.get_time(calling_entity)
