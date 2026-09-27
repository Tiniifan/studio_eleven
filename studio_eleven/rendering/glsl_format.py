"""Whitespace only formatter for GLSL: names, operators and numbers are never touched."""
import re

INDENT = "    "
WRAP_COLUMN = 92

TOKEN = re.compile(r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<number>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?[fFuU]*)
  | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op><<=|>>=|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|==|!=|<=|>=|&&|\|\||\^\^|<<|>>|[-+*/%=<>!&|^~?:.,;(){}\[\]])
""", re.X | re.S)

KEYWORDS_BEFORE_PAREN = {"if", "for", "while", "switch", "return"}
WRAP_OPERATORS = {"&&", "||", "+", "-", "*", "/", "?", ":"}
SPACED_OPERATORS = {"=", "==", "!=", "<=", ">=", "<", ">", "&&", "||", "^^", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
                    "<<", ">>", "<<=", ">>=", "?", ":", "+", "-", "*", "/", "%", "&", "|", "^"}


def tokenize(text):
    """Returns the (kind, value) list of the code, preprocessor lines are single tokens."""
    tokens = []
    code = []

    def flush():
        source = "\n".join(code)
        position = 0
        while position < len(source):
            if source[position].isspace():
                position += 1
                continue
            match = TOKEN.match(source, position)
            if match is None:
                raise ValueError(f"Unknown GLSL character {source[position]!r}")
            tokens.append((match.lastgroup, match.group()))
            position = match.end()
        code.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            flush()
            tokens.append(("directive", " ".join(line.split())))
        else:
            code.append(line)
    flush()

    return tokens


def is_unary(previous):
    if previous is None:
        return True
    kind, value = previous
    if kind in ("number",):
        return False
    if kind == "ident":
        return value in KEYWORDS_BEFORE_PAREN
    return value not in (")", "]")


def format_glsl(text):
    tokens = tokenize(text)
    lines = []
    line = []
    depth = 0
    paren = 0
    previous = None
    wrapped = False
    is_unary_operator = [False]

    def current_text():
        return "".join(line)

    def emit_line():
        nonlocal line, wrapped
        content = current_text().rstrip()
        if content:
            lines.append(content)
        line = []
        wrapped = False

    def indent():
        return INDENT * depth + (INDENT * 2 if wrapped else "")

    def add(piece, space_before):
        if not line:
            line.append(indent())
        elif space_before:
            line.append(" ")
        line.append(piece)

    for index, (kind, value) in enumerate(tokens):
        following = tokens[index + 1] if index + 1 < len(tokens) else None

        if kind == "directive":
            emit_line()
            if lines and lines[-1] != "" and not lines[-1].startswith("#") and not lines[-1].startswith("precision"):
                lines.append("")
            lines.append(value)
            previous = None
            continue

        if kind == "comment":
            add(value, True)
            if value.startswith("//"):
                emit_line()
            previous = (kind, value)
            continue

        if value == "{":
            if depth == 0 and lines and lines[-1] != "" and line:
                lines.insert(len(lines), "")
            add(value, True)
            emit_line()
            depth += 1
        elif value == "}":
            emit_line()
            depth -= 1
            add(value, False)
            if not (following and following[1] in (";", "else")) and not (following and following[1] in ("(", ")", ",")):
                emit_line()
                if depth == 0:
                    lines.append("")
        elif value == ";":
            line_text = current_text()
            add(value, False)
            if paren == 0:
                emit_line()
                if depth == 0 and line_text.strip() == "}":
                    lines.append("")
        else:
            space = True
            if value == ",":
                space = False
            elif value in (")", "]", "."):
                space = False
            elif value in ("(", "["):
                space = previous is not None and ((previous[0] == "ident" and previous[1] in KEYWORDS_BEFORE_PAREN)
                                                  or (previous[0] == "op" and (previous[1] in SPACED_OPERATORS or previous[1] == ",")
                                                      and not is_unary_operator[0]))
                if previous is not None and previous[1] in (")", "]") and value == "[":
                    space = False
            elif previous is not None and previous[1] in ("(", "[", ".", "!", "~"):
                space = False
            elif previous is not None and previous[1] in ("-", "+", "++", "--") and is_unary_operator[0]:
                space = False
            elif value in ("++", "--"):
                space = False
            elif value in ("!", "~"):
                space = previous is not None and previous[0] in ("ident", "number")

            if value in ("(", "["):
                paren += 1
            elif value in (")", "]"):
                paren -= 1

            column = len(current_text())
            if column > WRAP_COLUMN and value in WRAP_OPERATORS and not is_unary(previous):
                emit_line()
                wrapped = True
            add(value, space)
            if value == "," and len(current_text()) > WRAP_COLUMN and paren >= 1:
                emit_line()
                wrapped = True

        # A sign is unary when it follows an operator, an opening bracket, a comma or nothing
        is_unary_operator = [value in ("-", "+") and is_unary(previous)]
        previous = (kind, value)

    emit_line()

    while lines and lines[-1] == "":
        lines.pop()

    # Collapse the blank lines the rules above may stack
    result = []
    for content in lines:
        if content == "" and result and result[-1] == "":
            continue
        result.append(content)

    return "\n".join(result) + "\n"


def same_tokens(first, second):
    return tokenize(first) == tokenize(second)
