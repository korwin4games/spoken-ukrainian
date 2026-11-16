"""Run contract assertions with the system Lua 5.4 shared library; no pip packages."""
import ctypes
from ctypes.util import find_library


def run_lua(source):
    name = find_library("lua5.4")
    if not name:
        raise RuntimeError("Contract tests require the system Lua 5.4 shared library (liblua5.4)")
    lib = ctypes.CDLL(name)
    state = ctypes.c_void_p
    lib.luaL_newstate.restype = state
    lib.luaL_openlibs.argtypes = [state]
    lib.luaL_loadstring.argtypes = [state, ctypes.c_char_p]
    lib.luaL_loadstring.restype = ctypes.c_int
    lib.lua_pcallk.argtypes = [state, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_ssize_t, ctypes.c_void_p]
    lib.lua_pcallk.restype = ctypes.c_int
    lib.lua_tolstring.argtypes = [state, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lib.lua_tolstring.restype = ctypes.c_char_p
    lib.lua_close.argtypes = [state]
    vm = lib.luaL_newstate()
    if not vm:
        raise RuntimeError("Cannot allocate Lua state")
    try:
        lib.luaL_openlibs(vm)
        status = lib.luaL_loadstring(vm, source.encode("utf-8"))
        if status == 0:
            status = lib.lua_pcallk(vm, 0, 0, 0, 0, None)
        if status != 0:
            message = lib.lua_tolstring(vm, -1, None)
            raise AssertionError(message.decode("utf-8", errors="replace") if message else "Lua failure")
    finally:
        lib.lua_close(vm)
