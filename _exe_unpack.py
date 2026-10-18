# -*- coding: utf-8 -*-
"""
解析 PyInstaller onefile exe 的 CArchive，解出内嵌的 TxtSeeker.html，
与源文件逐字节比对 md5 —— 证明「exe 里装的就是刚改好的那一版」。
用法：python _exe_unpack.py <exe路径> <源html路径>
"""
import hashlib
import struct
import sys
import zlib

MAGIC = b"MEI\014\013\012\013\016"
COOKIE = 88
HDR = 18


def entries(data):
    i = data.rfind(MAGIC)
    if i < 0:
        raise RuntimeError("未找到 PyInstaller cookie")
    pkg_len, toc_off, toc_len, _pyvers = struct.unpack("!IIII", data[i + 8:i + 24])
    pkg_start = i + COOKIE - pkg_len
    p = pkg_start + toc_off
    end = pkg_start + toc_off + toc_len
    out = []
    while p + HDR <= end:
        elen, eoff, clen, _ulen, flag, _tcode = struct.unpack("!IIIIBB", data[p:p + HDR])
        name = data[p + HDR:p + elen].split(b"\0")[0].decode("utf-8", "replace")
        out.append((name, flag, pkg_start + eoff, clen))
        p += elen
    return out


def main():
    exe, src = sys.argv[1], sys.argv[2]
    data = open(exe, "rb").read()
    ents = entries(data)
    print(f"TOC 条目数: {len(ents)}")
    found = None
    for name, flag, off, clen in ents:
        raw = data[off:off + clen]
        if flag:
            raw = zlib.decompress(raw)
        if name == "TxtSeeker.html" or name.endswith("TxtSeeker.html"):
            found = (name, raw)
    if not found:
        print("❌ 未解出 TxtSeeker.html；候选条目：")
        for name, _f, _o, _c in ents:
            if name.endswith(".html"):
                print("   ", name)
        return 1
    name, raw = found
    src_raw = open(src, "rb").read()
    md5_in = hashlib.md5(raw).hexdigest()
    md5_src = hashlib.md5(src_raw).hexdigest()
    print(f"解出条目: {name}")
    print(f"exe 内嵌: {len(raw)} bytes  md5={md5_in}")
    print(f"源文件:   {len(src_raw)} bytes  md5={md5_src}")
    if raw == src_raw:
        print("✅ 内嵌载荷与源文件逐字节一致")
        return 0
    print("❌ 不一致！")
    return 1


if __name__ == "__main__":
    sys.exit(main())
