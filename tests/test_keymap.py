from threeds_pad import keymap

SAMPLE = r'''
[Controls]
profile=0
profile\default=true
profiles\1\button_a="code:76,engine:keyboard"
profiles\1\button_a\default=false
profiles\1\button_b="code:75,engine:keyboard"
profiles\1\button_x="engine:sdl,guid:abc,button:2,port:0"
profiles\1\button_start="code:16777220,engine:keyboard"
profiles\1\circle_pad="down:code$083$1engine$0keyboard,engine:analog_from_button,left:code$065$1engine$0keyboard,modifier:code$068$1engine$0keyboard,modifier_scale:0.500000,right:code$068$1engine$0keyboard,up:code$087$1engine$0keyboard"
profiles\size=1
'''


def test_parse():
    qt, warn = keymap.parse_config_text(SAMPLE)
    assert qt["A"] == ord("L") and qt["B"] == ord("K")
    assert "X" not in qt and any("X" in w for w in warn)
    assert qt["START"] == 0x01000004
    assert qt["CUP"] == ord("W") and qt["CLEFT"] == ord("A")
    assert qt["Y"] == ord("X")  # 書かれていないものは初期設定


def test_mac_codes():
    assert keymap.qt_to_mac(ord("A")) == 0
    assert keymap.qt_to_mac(0x01000012) == 123
    assert keymap.qt_to_mac(0x01000004) == 36


def test_load_defaults(tmp_path):
    mac, warn, path = keymap.load_keymap(str(tmp_path / "none.ini"))
    assert mac["A"] == 0 and mac["CUP"] == 126
