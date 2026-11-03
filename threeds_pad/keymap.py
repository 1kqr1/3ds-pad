"""Azahar の qt-config.ini からキーボード割り当てを読み取り、macOS のキーコードに変換する。"""
import configparser
import os
import re

CONFIG_CANDIDATES = [
    "~/Library/Application Support/Azahar/config/qt-config.ini",
    "~/Library/Application Support/Lime3DS/config/qt-config.ini",
    "~/Library/Application Support/Citra/config/qt-config.ini",
]

# --- Qt のキーコード → macOS の仮想キーコード -----------------------------
_MAC_LETTERS = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7, "C": 8, "V": 9,
    "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17, "O": 31, "U": 32,
    "I": 34, "P": 35, "L": 37, "J": 38, "K": 40, "N": 45, "M": 46,
}
_MAC_DIGITS = {"1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29}
_MAC_PUNCT = {
    ord("="): 24, ord("-"): 27, ord("]"): 30, ord("["): 33, ord("'"): 39, ord(";"): 41,
    ord("\\"): 42, ord(","): 43, ord("/"): 44, ord("."): 47, ord("`"): 50, ord(" "): 49,
}
_QT_SPECIAL = {
    0x01000000: 53,   # Escape
    0x01000001: 48,   # Tab
    0x01000003: 51,   # Backspace
    0x01000004: 36,   # Return
    0x01000005: 76,   # Enter (テンキー)
    0x01000007: 117,  # Delete
    0x01000010: 115,  # Home
    0x01000011: 119,  # End
    0x01000012: 123,  # Left
    0x01000013: 126,  # Up
    0x01000014: 124,  # Right
    0x01000015: 125,  # Down
    0x01000016: 116,  # PageUp
    0x01000017: 121,  # PageDown
    0x01000020: 56,   # Shift
    0x01000021: 59,   # Control (Qt上のCtrl = Macの⌘の場合あり)
    0x01000022: 55,   # Meta
    0x01000023: 58,   # Alt/Option
}
for _i, _code in enumerate([122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111]):
    _QT_SPECIAL[0x01000030 + _i] = _code  # F1〜F12


def qt_to_mac(qt_code):
    """Qt::Key の数値を macOS の仮想キーコードに変換。変換できなければ None。"""
    if qt_code in _QT_SPECIAL:
        return _QT_SPECIAL[qt_code]
    if 0x41 <= qt_code <= 0x5A:
        return _MAC_LETTERS.get(chr(qt_code))
    if 0x30 <= qt_code <= 0x39:
        return _MAC_DIGITS.get(chr(qt_code))
    return _MAC_PUNCT.get(qt_code)


# --- 初期設定（Azahar の既定値と同じ） -------------------------------------
DEFAULT_QT = {
    "A": ord("A"), "B": ord("S"), "X": ord("Z"), "Y": ord("X"),
    "L": ord("Q"), "R": ord("W"), "ZL": ord("1"), "ZR": ord("2"),
    "START": ord("M"), "SELECT": ord("N"), "HOME": ord("B"),
    "UP": ord("T"), "DOWN": ord("G"), "LEFT": ord("F"), "RIGHT": ord("H"),
    "CUP": 0x01000013, "CDOWN": 0x01000015, "CLEFT": 0x01000012, "CRIGHT": 0x01000014,
}

_BUTTON_KEYS = {
    "button_a": "A", "button_b": "B", "button_x": "X", "button_y": "Y",
    "button_l": "L", "button_r": "R", "button_zl": "ZL", "button_zr": "ZR",
    "button_start": "START", "button_select": "SELECT", "button_home": "HOME",
    "button_up": "UP", "button_down": "DOWN", "button_left": "LEFT", "button_right": "RIGHT",
}

_CODE_RE = re.compile(r"code:(\d+)")
_ANALOG_RE = re.compile(r"(up|down|left|right):code\$0(\d+)\$1engine\$0keyboard")


def find_config():
    for c in CONFIG_CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.exists(p):
            return p
    return None


def _strip(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        v = v[1:-1]
    return v


def parse_config_text(text):
    """qt-config.ini の内容から {ボタン名: Qtキーコード} と警告一覧を返す。"""
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(text)
    if not cp.has_section("Controls"):
        return dict(DEFAULT_QT), ["[Controls] が見つからないため初期設定を使います"]
    sec = cp["Controls"]

    try:
        idx = int(_strip(sec.get("profile", "0"))) + 1
    except ValueError:
        idx = 1
    prefix = f"profiles\\{idx}\\"

    def get(name):
        for key in (prefix + name, name):
            if key in sec:
                return _strip(sec[key])
        return None

    result, warnings = dict(DEFAULT_QT), []
    for key, btn in _BUTTON_KEYS.items():
        v = get(key)
        if v is None:
            continue
        if "engine:keyboard" in v and (m := _CODE_RE.search(v)):
            result[btn] = int(m.group(1))
        else:
            result.pop(btn, None)
            warnings.append(f"{btn} はキーボード以外に割り当てられています")

    cp_val = get("circle_pad")
    if cp_val:
        found = dict(_ANALOG_RE.findall(cp_val))
        if found:
            for d in ("up", "down", "left", "right"):
                if d in found:
                    result["C" + d.upper()] = int(found[d])
        elif "analog_from_button" not in cp_val:
            for d in ("CUP", "CDOWN", "CLEFT", "CRIGHT"):
                result.pop(d, None)
            warnings.append("スライドパッドがキーボード以外に割り当てられています")
    return result, warnings


def load_keymap(path=None):
    """{ボタン名: macキーコード}, 警告, 読み込んだパス を返す。"""
    path = path or find_config()
    if path:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                qt, warnings = parse_config_text(f.read())
        except OSError as e:
            qt, warnings = dict(DEFAULT_QT), [f"設定ファイルを読めません: {e}"]
    else:
        qt, warnings = dict(DEFAULT_QT), ["Azahar の設定ファイルが見つからないため初期設定を使います"]
    mac = {}
    for btn, code in qt.items():
        mk = qt_to_mac(code)
        if mk is None:
            warnings.append(f"{btn} のキー (Qt {code}) はMacのキーに変換できません")
        else:
            mac[btn] = mk
    return mac, warnings, path
