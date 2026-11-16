"""A lexer and recursive-descent parser for a deliberately restricted Lua data subset."""
from dataclasses import dataclass
import math
import re


class SourceError(ValueError):
    def __init__(self, file, line, message, kind="source"):
        self.file, self.line, self.message, self.kind = file, line, message, kind
        super().__init__(f"{file}:{line}: {message}")


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int


@dataclass(frozen=True)
class Node:
    value: object
    file: str
    line: int
    column: int


@dataclass(frozen=True)
class Entry:
    key: Node
    value: Node
    positional: bool = False


@dataclass
class Table:
    entries: list[Entry]

    def effective(self):
        result = {}
        for entry in self.entries:
            if entry.value.value is None:
                result.pop(entry.key.value, None)
            else:
                result[entry.key.value] = entry
        return result

    def get(self, key):
        entry = self.effective().get(key)
        return entry.value if entry else None


class Lexer:
    def __init__(self, text, file="<input>"):
        self.text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.file, self.pos, self.line, self.column = file, 0, 1, 1

    def error(self, message):
        raise SourceError(self.file, self.line, message, kind="syntax")

    def advance(self, count=1):
        part = self.text[self.pos:self.pos + count]
        lines = part.count("\n")
        self.line += lines
        self.column = len(part.rsplit("\n", 1)[-1]) + 1 if lines else self.column + count
        self.pos += count
        return part

    def long_string(self):
        start = self.pos
        if not self.text.startswith("[", start):
            return None
        end = start + 1
        while self.text.startswith("=", end):
            end += 1
        if not self.text.startswith("[", end):
            return None
        close = "]" + self.text[start + 1:end] + "]"
        finish = self.text.find(close, end + 1)
        if finish < 0:
            self.error("Unterminated long-bracket string or comment")
        content = self.text[end + 1:finish]
        self.advance(finish + len(close) - start)
        return content[1:] if content.startswith("\n") else content

    def quoted_string(self):
        quote = self.advance()
        data = bytearray()
        escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
                   "t": "\t", "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}
        while self.pos < len(self.text):
            char = self.advance()
            if char == quote:
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError:
                    self.error("String contains bytes that are not valid UTF-8")
            if char == "\n":
                self.error("Unescaped newline in quoted string")
            if char != "\\":
                data.extend(char.encode("utf-8"))
                continue
            if self.pos == len(self.text):
                self.error("Unterminated escape")
            escaped = self.advance()
            if escaped.isascii() and escaped.isdigit():
                digits = escaped
                while len(digits) < 3 and self.pos < len(self.text) and self.text[self.pos] in "0123456789":
                    digits += self.advance()
                value = int(digits)
                if value > 255:
                    self.error("Decimal escape exceeds one byte")
                data.append(value)
            elif escaped in escapes:
                data.extend(escapes[escaped].encode("utf-8"))
            else:
                self.error("Unsupported quoted-string escape")
        self.error("Unterminated quoted string")

    def tokens(self):
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char.isspace() or (self.pos == 0 and char == "\ufeff"):
                self.advance()
                continue
            if self.text.startswith("--", self.pos):
                self.advance(2)
                if self.long_string() is None:
                    end = self.text.find("\n", self.pos)
                    self.advance((len(self.text) if end < 0 else end) - self.pos)
                continue
            line, column = self.line, self.column
            if char in "\"'":
                yield Token("string", self.quoted_string(), line, column)
                continue
            long = self.long_string() if char == "[" else None
            if long is not None:
                yield Token("string", long, line, column)
                continue
            if char in "0123456789" or (char == "." and self.text[self.pos + 1:self.pos + 2].isdigit()):
                match = re.match(r"(?:0[xX][0-9a-fA-F]+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", self.text[self.pos:])
                raw = match.group()
                self.advance(len(raw))
                value = int(raw, 16) if raw.lower().startswith("0x") else float(raw) if any(c in raw for c in ".eE") else int(raw)
                if abs(value) > 2 ** 53 or not math.isfinite(value):
                    self.error("Number outside the supported exact finite range")
                yield Token("number", value, line, column)
                continue
            if char.isascii() and (char.isalpha() or char == "_"):
                match = re.match(r"[a-zA-Z_][a-zA-Z_0-9]*", self.text[self.pos:])
                name = self.advance(len(match.group()))
                yield Token("name", name, line, column)
                continue
            operator = next((op for op in ("...", "==", "~=") if self.text.startswith(op, self.pos)), None)
            if operator:
                self.advance(len(operator))
                yield Token("symbol", operator, line, column)
            elif char in "{}[]=,;().-":
                self.advance()
                yield Token("symbol", char, line, column)
            else:
                self.error("Unsupported character or operator")
        yield Token("eof", None, self.line, self.column)


KEYWORDS = frozenset("and break do else elseif end false for function if in local nil not or repeat return then true until while".split())


class Parser:
    def __init__(self, text, file="<input>"):
        self.file = file
        self.tokens = list(Lexer(text, file).tokens())
        self.index = 0

    @property
    def token(self):
        return self.tokens[self.index]

    def fail(self, message):
        raise SourceError(self.file, self.token.line, message, kind="syntax")

    def at(self, value):
        kind = "name" if value and (value[0].isalpha() or value[0] == "_") else "symbol"
        return self.token.kind == kind and self.token.value == value

    def take(self, value):
        if not self.at(value):
            self.fail("Expected syntax token " + str(value))
        token = self.token
        self.index += 1
        return token

    def node(self, value, token):
        return Node(value, self.file, token.line, token.column)

    def value(self, depth=0):
        if depth > 128:
            self.fail("Table nesting limit exceeded")
        token = self.token
        if token.kind in ("number", "string"):
            self.index += 1
            return self.node(token.value, token)
        if token.value in ("nil", "true", "false"):
            self.index += 1
            return self.node({"nil": None, "true": True, "false": False}[token.value], token)
        if token.value == "-":
            self.index += 1
            number = self.token
            if number.kind != "number":
                self.fail("Unary minus requires a numeric literal")
            self.index += 1
            return self.node(-number.value, token)
        if token.value != "{":
            self.fail("Expected a literal or table; executable expressions are unsupported")
        self.index += 1
        entries, position, key_kinds = [], 1, {}
        while not self.at("}"):
            positional = False
            if self.at("["):
                self.index += 1
                key = self.value(depth + 1)
                if type(key.value) not in (str, int, float):
                    self.fail("Only string and numeric table keys are supported")
                self.take("]")
                self.take("=")
                value = self.value(depth + 1)
            elif self.token.kind == "name" and self.token.value not in KEYWORDS and self.tokens[self.index + 1].kind == "symbol" and self.tokens[self.index + 1].value == "=":
                key = self.node(self.token.value, self.token)
                self.index += 2
                value = self.value(depth + 1)
            else:
                key = self.node(position, self.token)
                position += 1
                positional = True
                value = self.value(depth + 1)
            if key.value in key_kinds and key_kinds[key.value] != positional:
                self.fail("Colliding positional and keyed fields have unspecified Lua constructor order")
            key_kinds[key.value] = positional
            entries.append(Entry(key, value, positional))
            if self.at(",") or self.at(";"):
                self.index += 1
            elif not self.at("}"):
                self.fail("Expected table field separator")
        self.take("}")
        return self.node(Table(entries), token)

    def expect_end(self):
        if self.token.kind != "eof":
            self.fail("Unsupported trailing syntax")


def parse_value(text, file="<input>"):
    parser = Parser(text, file)
    node = parser.value()
    parser.expect_end()
    return node


def parse_file(text, category, file="<input>"):
    """Recognize the pinned data-file wrappers without interpreting control flow."""
    parser = Parser(text, file)
    for value in ("local", "_", ",", "addonTable", "=", "..."):
        parser.take(value)
    direct = parser.at("addonTable")
    if direct:
        for value in ("addonTable", ".", category, "="):
            parser.take(value)
        table = parser.value()
        mode = "initialize"
        parser.expect_end()
    else:
        parser.take("local")
        if parser.token.kind != "name" or parser.token.value in KEYWORDS:
            parser.fail("Expected local data-table identifier")
        variable = parser.token.value
        parser.index += 1
        parser.take("=")
        table = parser.value()
        target = f"addonTable.{category}"
        if category == "gossip":
            footer = f'''if {target} then
              for k, v in pairs({variable}) do
                if type({target}[k]) == "table" and type(v) == "table" then
                  for vk, vv in pairs(v) do {target}[k][vk] = vv end
                else {target}[k] = v end
              end
            else {target} = {variable} end'''
            mode = "gossip"
        elif category == "object":
            footer = f"for k, v in pairs({variable}) do {target}[k] = v end"
            mode = "merge"
        else:
            footer = f'''if {target} then
              for k, v in pairs({variable}) do {target}[k] = v end
            else {target} = {variable} end'''
            mode = "merge"
        expected = list(Lexer(footer).tokens())[:-1]
        for token in expected:
            if (parser.token.kind, parser.token.value) != (token.kind, token.value):
                parser.fail("Unsupported data-file merge wrapper")
            parser.index += 1
        parser.expect_end()
    if not isinstance(table.value, Table):
        parser.fail("Data initializer must be a table")
    return table, mode
