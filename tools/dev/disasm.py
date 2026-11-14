#!/usr/bin/env python3
"""Minimal MIPS32 LE disassembler for dev analysis."""
import struct

R = ["zero","at","v0","v1","a0","a1","a2","a3","t0","t1","t2","t3",
     "t4","t5","t6","t7","s0","s1","s2","s3","s4","s5","s6","s7",
     "t8","t9","k0","k1","gp","sp","fp","ra"]

def dis(w, va):
    op = w>>26; rs=(w>>21)&31; rt=(w>>16)&31; rd=(w>>11)&31; sa=(w>>6)&31
    imm=w&0xffff; si=imm-0x10000 if imm&0x8000 else imm
    if w==0: return "nop"
    if op==0:
        f=w&0x3f
        return {0x20:f"add {R[rd]},{R[rs]},{R[rt]}",
                0x21:f"addu {R[rd]},{R[rs]},{R[rt]}",
                0x22:f"sub {R[rd]},{R[rs]},{R[rt]}",
                0x23:f"subu {R[rd]},{R[rs]},{R[rt]}",
                0x24:f"and {R[rd]},{R[rs]},{R[rt]}",
                0x25:f"or {R[rd]},{R[rs]},{R[rt]}",
                0x26:f"xor {R[rd]},{R[rs]},{R[rt]}",
                0x27:f"nor {R[rd]},{R[rs]},{R[rt]}",
                0x00:f"sll {R[rd]},{R[rt]},{sa}",
                0x02:f"srl {R[rd]},{R[rt]},{sa}",
                0x03:f"sra {R[rd]},{R[rt]},{sa}",
                0x04:f"sllv {R[rd]},{R[rt]},{R[rs]}",
                0x06:f"srlv {R[rd]},{R[rt]},{R[rs]}",
                0x08:f"jr {R[rs]}",
                0x09:f"jalr {R[rd]},{R[rs]}",
                0x2a:f"slt {R[rd]},{R[rs]},{R[rt]}",
                0x2b:f"sltu {R[rd]},{R[rs]},{R[rt]}",
                0x10:f"mfhi {R[rd]}",0x12:f"mflo {R[rd]}",
                0x11:f"mthi {R[rs]}",0x13:f"mtlo {R[rs]}",
                0x18:f"mult {R[rs]},{R[rt]}",0x19:f"multu {R[rs]},{R[rt]}",
                0x1a:f"div {R[rs]},{R[rt]}",0x1b:f"divu {R[rs]},{R[rt]}",
                0x0d:f"break",0x0c:f"syscall",
                0x01:f"movci {w:08x}"}.get(f,f"special.{f:#x} {w:08x}")
    if op==0x0f: return f"lui {R[rt]},{imm:#x}"
    if op==9: return f"addiu {R[rt]},{R[rs]},{si}"
    if op==8: return f"addi {R[rt]},{R[rs]},{si}"
    if op==0x23: return f"lw {R[rt]},{si}({R[rs]})"
    if op==0x2b: return f"sw {R[rt]},{si}({R[rs]})"
    if op==0x20: return f"lb {R[rt]},{si}({R[rs]})"
    if op==0x24: return f"lbu {R[rt]},{si}({R[rs]})"
    if op==0x28: return f"sb {R[rt]},{si}({R[rs]})"
    if op==0x21: return f"lh {R[rt]},{si}({R[rs]})"
    if op==0x25: return f"lhu {R[rt]},{si}({R[rs]})"
    if op==0x29: return f"sh {R[rt]},{si}({R[rs]})"
    if op==0x30: return f"ll {R[rt]},{si}({R[rs]})"
    if op==0x38: return f"sc {R[rt]},{si}({R[rs]})"
    if op==2: return f"j {((va+4)&0xf0000000)|((w&0x3ffffff)<<2):#x}"
    if op==3: return f"jal {((va+4)&0xf0000000)|((w&0x3ffffff)<<2):#x}"
    if op==4: return f"beq {R[rs]},{R[rt]}->{(va+4+si*4)&0xffffffff:#x}"
    if op==5: return f"bne {R[rs]},{R[rt]}->{(va+4+si*4)&0xffffffff:#x}"
    if op==6: return f"blez {R[rs]}->{(va+4+si*4)&0xffffffff:#x}"
    if op==7: return f"bgtz {R[rs]}->{(va+4+si*4)&0xffffffff:#x}"
    if op==0xa: return f"slti {R[rt]},{R[rs]},{si}"
    if op==0xb: return f"sltiu {R[rt]},{R[rs]},{si}"
    if op==0xc: return f"andi {R[rt]},{R[rs]},{imm:#x}"
    if op==0xd: return f"ori {R[rt]},{R[rs]},{imm:#x}"
    if op==0xe: return f"xori {R[rt]},{R[rs]},{imm:#x}"
    if op==1:
        sub=(w>>16)&31; tgt=(va+4+si*4)&0xffffffff
        return {0:f"bltz {R[rs]}->{tgt:#x}",1:f"bgez {R[rs]}->{tgt:#x}",
                0x10:f"bltzal {R[rs]}->{tgt:#x}",0x11:f"bgezal {R[rs]}->{tgt:#x}"}.get(sub,f"regimm.{sub} {w:08x}")
    if op==0x1c:
        f=w&0x3f
        return {2:f"mul {R[rd]},{R[rs]},{R[rt]}",0x20:f"clz {R[rd]},{R[rs]}",
                0x21:f"clo {R[rd]},{R[rs]}"}.get(f,f"special2.{f:#x} {w:08x}")
    if op==0x1f:
        f=w&0x3f; b5=(w>>6)&31
        if f==0x20: return f"ins {R[rt]},{R[rs]},{sa},{b5+1}"
        if f==0: return f"ext {R[rt]},{R[rs]},{sa},{b5+1}"
        if f==0x3b: return f"rdhwr {R[rt]},hw{R[rd]}"
        if f==2 and sa==2: return f"wsbh {R[rd]},{R[rt]}"
        if f==2 and sa==0x18: return f"seh {R[rd]},{R[rt]}"
        if f==0x10 and sa==0x10: return f"seb {R[rd]},{R[rt]}"
        return f"special3.{f:#x} {w:08x}"
    if op==0x33: return f"pref {R[rt]},{si}({R[rs]})"
    if op==0x22: return f"lwl {R[rt]},{si}({R[rs]})"
    if op==0x26: return f"lwr {R[rt]},{si}({R[rs]})"
    if op==0x2a: return f"swl {R[rt]},{si}({R[rs]})"
    if op==0x2e: return f"swr {R[rt]},{si}({R[rs]})"
    if op==0x3b: return f"rdhwr/gte {w:08x}"
    return f"op{op:#x} {w:08x}"

def dump(blob, start, n, vabase=0):
    out=[]
    for i in range(n):
        o=start+i*4
        if o+4>len(blob): break
        w=struct.unpack_from("<I",blob,o)[0]
        va=vabase+o
        out.append(f"0x{va:08x}: {w:08x}  {dis(w,va)}")
    return "\n".join(out)

if __name__=="__main__":
    import sys
    blob=open(sys.argv[1],"rb").read()
    start=int(sys.argv[2],0); n=int(sys.argv[3],0); vb=int(sys.argv[4],0)
    print(dump(blob,start,n,vb))
