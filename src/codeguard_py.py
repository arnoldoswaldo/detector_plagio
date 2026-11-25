import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


try:
    from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker, Token
    from antlr4.error.ErrorListener import ErrorListener
    from antlr4.TokenStreamRewriter import TokenStreamRewriter
except ImportError as exc:
    sys.stderr.write(
        "[ERROR] No se encontró 'antlr4-python3-runtime'.\n"
        "Instálalo ejecutando: pip install antlr4-python3-runtime\n"
    )
    raise SystemExit(1) from exc


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(CURRENT_DIR, "generated")
if GENERATED_DIR not in sys.path:
    sys.path.insert(0, GENERATED_DIR)

try:
    from Python3Lexer import Python3Lexer
    from Python3Parser import Python3Parser
    from Python3ParserListener import Python3ParserListener
except ImportError as exc:
    sys.stderr.write(
        "[ERROR] No se encontraron los archivos compilados de la gramática en 'src/generated/'.\n"
        "Asegúrate de haber ejecutado:\n"
        "  cd gramatica && python3 transformGrammar.py\n"
        "  antlr4 -Dlanguage=Python3 -o ../src/generated Python3Lexer.g4 Python3Parser.g4\n"
        "  cp Python3LexerBase.py Python3ParserBase.py ../src/generated/\n"
    )
    raise SystemExit(1) from exc


PYTHON_BUILTINS: Set[str] = {
    "abs", "all", "any", "bin", "bool", "chr", "dict", "divmod", "enumerate",
    "filter", "float", "format", "hex", "input", "int", "isinstance", "iter",
    "len", "list", "map", "max", "min", "next", "oct", "open", "ord", "pow",
    "print", "range", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "type", "zip",
}

PYTHON_CONSTANTS: Set[str] = {"True", "False", "None"}


@dataclass
class SymbolInfo:
    """Representa una entrada en la tabla de símbolos local de una función."""
    original_name: str
    role: str
    normalized_id: str
    uses: int = 0


    def_intervals: List[Tuple[int, int]] = field(default_factory=list)

    token_refs: List[Token] = field(default_factory=list)


@dataclass
class FunctionScope:
    """Ámbito semántico aislado para cada definición de función (def)."""
    original_name: str
    canon_name: str
    start_token: Token
    start_line: int
    symbols: Dict[str, SymbolInfo] = field(default_factory=dict)
    param_counter: int = 0
    local_counter: int = 0

    tagged_tokens: List[Tuple[int, str, Optional[str], bool]] = field(default_factory=list)

    normalized_tokens: List[str] = field(default_factory=list)

    dead_variables: List[str] = field(default_factory=list)

    def register_param(self, name: str, token: Optional[Token] = None) -> SymbolInfo:
        """Registra un parámetro formal en la tabla de símbolos de la función."""
        if name not in self.symbols:
            self.param_counter += 1
            norm_id = f"PARAM_{self.param_counter}"
            self.symbols[name] = SymbolInfo(
                original_name=name,
                role="PARAM",
                normalized_id=norm_id,
                uses=0,
            )
        sym = self.symbols[name]
        if token is not None:
            sym.token_refs.append(token)
        return sym

    def register_local(
        self,
        name: str,
        token: Optional[Token] = None,
        def_interval: Optional[Tuple[int, int]] = None,
        initial_uses: int = 0,
    ) -> SymbolInfo:
        """Registra una variable local asignada y opcionalmente su intervalo Def."""
        if name not in self.symbols:
            self.local_counter += 1
            norm_id = f"LOCAL_{self.local_counter}"
            self.symbols[name] = SymbolInfo(
                original_name=name,
                role="LOCAL",
                normalized_id=norm_id,
                uses=initial_uses,
            )
        sym = self.symbols[name]
        if token is not None:
            sym.token_refs.append(token)
        if def_interval is not None and sym.role == "LOCAL":
            sym.def_intervals.append(def_interval)
        return sym


class SyntaxErrorCollector(ErrorListener):
    """Captura errores léxicos/sintácticos de ANTLR para reportarlos limpiamente."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: List[str] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e) -> None:
        self.errors.append(f"Línea {line}:{column} -> {msg}")


class PlagiarismListener(Python3ParserListener):
    """
    Recorre el AST generado por Python3Parser para:
      - Construir tablas de símbolos por función y rastrear definiciones/usos.
      - Normalizar identificadores según su rol semántico.
      - Eliminar asignaciones de código muerto (usos == 0) en el rewriter de canonización.
      - Insertar alertas de plagio en el rewriter de anotación.
    """

    def __init__(self, token_stream: CommonTokenStream, source_text: str) -> None:
        super().__init__()
        self.token_stream = token_stream
        self.source_text = source_text


        self.canon_rewriter = TokenStreamRewriter(token_stream)
        self.annot_rewriter = TokenStreamRewriter(token_stream)


        self.scope_stack: List[FunctionScope] = []

        self.analyzed_functions: List[FunctionScope] = []


        self.user_functions: Dict[str, str] = {}
        self.func_counter: int = 0


        self.lhs_token_indices: Set[int] = set()


        self.deleted_token_indices: Set[int] = set()
        self.deleted_intervals: Set[Tuple[int, int]] = set()
        self.replaced_token_indices: Set[int] = set()

    @property
    def current_scope(self) -> Optional[FunctionScope]:
        """Retorna el ámbito de función activo en el tope de la pila."""
        return self.scope_stack[-1] if self.scope_stack else None

    def _safe_canon_replace(self, token: Token, text: str) -> None:
        """
        Reemplaza un token en canon_rewriter garantizando como máximo una operación
        de reemplazo por índice y evitando conflictos con tokens eliminados.
        """
        idx = token.tokenIndex
        if idx in self.deleted_token_indices or idx in self.replaced_token_indices:
            return
        self.replaced_token_indices.add(idx)
        self.canon_rewriter.replaceSingleToken(token, text)

    @staticmethod
    def _get_name_token(ctx) -> Optional[Token]:
        """
        Extrae el token identificador de un nodo sintáctico de forma compatible
        con distintas versiones de Python3Parser.g4 (regla 'name' o terminal 'NAME').
        """
        if ctx is None:
            return None
        if hasattr(ctx, "name") and callable(ctx.name) and ctx.name() is not None:
            return ctx.name().start
        if hasattr(ctx, "NAME") and callable(ctx.NAME) and ctx.NAME() is not None:
            return ctx.NAME().symbol
        return None

    def _extract_target_tokens(self, node) -> List[Token]:
        """
        Recorre recursivamente una expresión objetivo (LHS de asignación o for)
        y extrae los tokens de variables simples asignadas (excluyendo atributos
        como obj.attr o indexaciones como arr[i]).
        """
        tokens: List[Token] = []
        if node is None:
            return tokens


        if isinstance(node, Python3Parser.Atom_exprContext):
            if hasattr(node, "trailer") and len(node.trailer()) > 0:
                return tokens

        if isinstance(node, Python3Parser.AtomContext):
            tok = self._get_name_token(node)
            if tok is not None:
                tokens.append(tok)
                return tokens

        if hasattr(node, "children") and node.children:
            for child in node.children:
                tokens.extend(self._extract_target_tokens(child))
        return tokens

    def _get_single_stmt_removal_interval(
        self, ctx, target_tokens: List[Token]
    ) -> Optional[Tuple[int, int]]:
        """
        Determina si la asignación es la única sentencia en su línea y retorna
        el intervalo (start_token_idx, stop_token_idx) incluyendo el NEWLINE
        final para poder eliminar la línea completa si resulta ser código muerto.
        Compatible tanto con grammars-v4 actual (simple_stmts -> simple_stmt)
        como con variantes previas (simple_stmt -> small_stmt).
        """
        if len(target_tokens) != 1:
            return None

        parent = ctx.parentCtx
        while parent is not None:

            if hasattr(Python3Parser, "Simple_stmtsContext") and isinstance(
                parent, Python3Parser.Simple_stmtsContext
            ):
                if hasattr(parent, "simple_stmt") and len(parent.simple_stmt()) == 1:
                    return (parent.start.tokenIndex, parent.stop.tokenIndex)
                return None


            if hasattr(Python3Parser, "Simple_stmtContext") and isinstance(
                parent, Python3Parser.Simple_stmtContext
            ):
                if hasattr(parent, "small_stmt"):
                    if len(parent.small_stmt()) == 1:
                        return (parent.start.tokenIndex, parent.stop.tokenIndex)
                    return None

            parent = parent.parentCtx
        return None


    def enterFuncdef(self, ctx: Python3Parser.FuncdefContext) -> None:
        func_tok = self._get_name_token(ctx)
        orig_name = func_tok.text if func_tok else "anon_func"

        if orig_name not in self.user_functions:
            self.func_counter += 1
            self.user_functions[orig_name] = f"FUNC_{self.func_counter}"
        canon_name = self.user_functions[orig_name]

        if func_tok is not None:
            self._safe_canon_replace(func_tok, canon_name)

        scope = FunctionScope(
            original_name=orig_name,
            canon_name=canon_name,
            start_token=ctx.start,
            start_line=ctx.start.line,
        )
        scope.tagged_tokens.append((ctx.start.tokenIndex, "DEF", None, False))


        params_ctx = ctx.parameters()
        if params_ctx is not None and params_ctx.typedargslist() is not None:
            tfpdefs = params_ctx.typedargslist().tfpdef()
            for p_ctx in tfpdefs:
                p_tok = self._get_name_token(p_ctx)
                if p_tok is not None:
                    scope.register_param(p_tok.text, token=p_tok)
                    scope.tagged_tokens.append((p_tok.tokenIndex, "", p_tok.text, False))

        self.scope_stack.append(scope)

    def exitFuncdef(self, ctx: Python3Parser.FuncdefContext) -> None:
        scope = self.scope_stack.pop()


        local_deleted: Set[int] = set()
        for sym in scope.symbols.values():
            if sym.role == "LOCAL" and sym.uses == 0:
                sym.normalized_id = "DEAD_VAR"
                scope.dead_variables.append(sym.original_name)
                for start_idx, stop_idx in sym.def_intervals:
                    interval = (start_idx, stop_idx)
                    if interval not in self.deleted_intervals:
                        self.deleted_intervals.add(interval)
                        self.canon_rewriter.delete(
                            TokenStreamRewriter.DEFAULT_PROGRAM_NAME, start_idx, stop_idx
                        )
                    for idx in range(start_idx, stop_idx + 1):
                        local_deleted.add(idx)
                        self.deleted_token_indices.add(idx)


        active_local_idx = 0
        for sym in scope.symbols.values():
            if sym.role == "LOCAL" and sym.uses > 0:
                active_local_idx += 1
                sym.normalized_id = f"LOCAL_{active_local_idx}"

            if not (sym.role == "LOCAL" and sym.uses == 0):
                for tok in sym.token_refs:
                    if tok.tokenIndex not in local_deleted:
                        self._safe_canon_replace(tok, sym.normalized_id)


        clean_tokens: List[str] = []
        for idx, static_tag, sym_name, is_def in scope.tagged_tokens:
            if idx in local_deleted:
                continue
            if sym_name is None:
                clean_tokens.append(static_tag)
            else:
                sym = scope.symbols[sym_name]
                if sym.role == "LOCAL" and sym.uses == 0:
                    continue
                tag = f"DEF:{sym.normalized_id}" if is_def else sym.normalized_id
                clean_tokens.append(tag)

        scope.normalized_tokens = clean_tokens
        self.analyzed_functions.append(scope)


    def enterExpr_stmt(self, ctx: Python3Parser.Expr_stmtContext) -> None:
        scope = self.current_scope
        if scope is None:
            return

        has_assign = hasattr(ctx, "ASSIGN") and len(ctx.ASSIGN()) > 0
        has_annassign = (
            hasattr(ctx, "annassign")
            and ctx.annassign() is not None
            and ctx.annassign().test() is not None
        )
        has_augassign = hasattr(ctx, "augassign") and ctx.augassign() is not None

        if has_assign:

            lhs_exprs = ctx.testlist_star_expr()[:-1]
            target_tokens: List[Token] = []
            for expr in lhs_exprs:
                target_tokens.extend(self._extract_target_tokens(expr))


            stmt_interval = self._get_single_stmt_removal_interval(ctx, target_tokens)

            for tok in target_tokens:
                self.lhs_token_indices.add(tok.tokenIndex)
                scope.register_local(tok.text, token=tok, def_interval=stmt_interval)
                scope.tagged_tokens.append((tok.tokenIndex, "", tok.text, True))

        elif has_annassign:
            lhs_expr = ctx.testlist_star_expr(0)
            target_tokens = self._extract_target_tokens(lhs_expr)
            stmt_interval = self._get_single_stmt_removal_interval(ctx, target_tokens)
            for tok in target_tokens:
                self.lhs_token_indices.add(tok.tokenIndex)
                scope.register_local(tok.text, token=tok, def_interval=stmt_interval)
                scope.tagged_tokens.append((tok.tokenIndex, "", tok.text, True))

        elif has_augassign:

            lhs_expr = ctx.testlist_star_expr(0)
            target_tokens = self._extract_target_tokens(lhs_expr)
            for tok in target_tokens:
                self.lhs_token_indices.add(tok.tokenIndex)
                sym = scope.register_local(
                    tok.text, token=tok, def_interval=None, initial_uses=0
                )
                sym.uses += 1
                scope.tagged_tokens.append((tok.tokenIndex, "", tok.text, False))

    def enterFor_stmt(self, ctx: Python3Parser.For_stmtContext) -> None:
        scope = self.current_scope
        if scope is None:
            return
        scope.tagged_tokens.append((ctx.start.tokenIndex, "FOR", None, False))
        target_tokens = self._extract_target_tokens(ctx.exprlist())
        for tok in target_tokens:
            self.lhs_token_indices.add(tok.tokenIndex)

            scope.register_local(tok.text, token=tok, def_interval=None, initial_uses=1)
            scope.tagged_tokens.append((tok.tokenIndex, "", tok.text, False))


    def enterIf_stmt(self, ctx: Python3Parser.If_stmtContext) -> None:
        if self.current_scope:
            self.current_scope.tagged_tokens.append((ctx.start.tokenIndex, "IF", None, False))

    def enterWhile_stmt(self, ctx: Python3Parser.While_stmtContext) -> None:
        if self.current_scope:
            self.current_scope.tagged_tokens.append((ctx.start.tokenIndex, "WHILE", None, False))

    def enterReturn_stmt(self, ctx: Python3Parser.Return_stmtContext) -> None:
        if self.current_scope:
            self.current_scope.tagged_tokens.append((ctx.start.tokenIndex, "RETURN", None, False))

    def enterComp_op(self, ctx: Python3Parser.Comp_opContext) -> None:
        if self.current_scope:
            self.current_scope.tagged_tokens.append(
                (ctx.start.tokenIndex, f"OP:{ctx.getText()}", None, False)
            )


    def enterAtom(self, ctx: Python3Parser.AtomContext) -> None:
        scope = self.current_scope
        if scope is None:
            return


        name_tok = self._get_name_token(ctx)
        if name_tok is not None:
            if name_tok.tokenIndex in self.lhs_token_indices:
                return

            ident = name_tok.text


            is_direct_call = False
            parent = ctx.parentCtx
            if isinstance(parent, Python3Parser.Atom_exprContext):
                if (
                    hasattr(parent, "trailer")
                    and len(parent.trailer()) > 0
                    and parent.trailer(0).getText().startswith("(")
                ):
                    is_direct_call = True

            if is_direct_call:
                if ident in PYTHON_BUILTINS:
                    scope.tagged_tokens.append((name_tok.tokenIndex, f"CALL:{ident}", None, False))
                elif ident in scope.symbols:
                    sym = scope.symbols[ident]
                    sym.uses += 1
                    sym.token_refs.append(name_tok)
                    scope.tagged_tokens.append((name_tok.tokenIndex, "", ident, False))
                else:
                    self._safe_canon_replace(name_tok, "CALL_USER")
                    scope.tagged_tokens.append((name_tok.tokenIndex, "CALL_USER", None, False))
                return


            if ident in scope.symbols:
                sym = scope.symbols[ident]
                sym.uses += 1
                sym.token_refs.append(name_tok)
                scope.tagged_tokens.append((name_tok.tokenIndex, "", ident, False))
            elif ident in PYTHON_CONSTANTS:
                scope.tagged_tokens.append((name_tok.tokenIndex, f"CONST:{ident}", None, False))
            else:
                self._safe_canon_replace(name_tok, "GLOBAL_VAR")
                scope.tagged_tokens.append((name_tok.tokenIndex, "GLOBAL_VAR", None, False))
            return


        if hasattr(ctx, "NUMBER") and ctx.NUMBER() is not None:
            tok = ctx.NUMBER().symbol
            scope.tagged_tokens.append((tok.tokenIndex, "NUM", None, False))
        elif hasattr(ctx, "STRING") and len(ctx.STRING()) > 0:
            tok = ctx.STRING(0).symbol
            scope.tagged_tokens.append((tok.tokenIndex, "STR", None, False))


    def annotate_plagiarism(
        self, func_scope: FunctionScope, similarity: float, matched_func_name: str
    ) -> None:
        """Inserta un comentario de alerta encima de la función sospechosa."""
        indent_spaces = " " * func_scope.start_token.column
        alert_line = (
            f"{indent_spaces}# [ALERTA DE PLAGIO: {similarity:.1f}% de similitud "
            f"con '{matched_func_name}']\n"
        )
        self.annot_rewriter.insertBeforeToken(func_scope.start_token, alert_line)

    def render_canonized_code(self) -> str:
        """
        Reconstruye el código canonizado preservando espacios e indentación válidos
        de Python 3, pero omitiendo comentarios (#) y líneas de código muerto.
        """
        tokens = self.token_stream.tokens
        if not tokens:
            return ""

        synthetic_types = {
            getattr(Python3Parser, "INDENT", -999),
            getattr(Python3Parser, "DEDENT", -999),
        }
        if tokens[0].type in synthetic_types:
            self._safe_canon_replace(tokens[0], "")

        last_kept_tok = tokens[0]
        for i in range(1, len(tokens)):
            curr_tok = tokens[i]
            prev_tok = tokens[i - 1]
            if curr_tok.type == Token.EOF:
                break
            if curr_tok.tokenIndex in self.deleted_token_indices:
                continue

            if curr_tok.type in synthetic_types:
                self._safe_canon_replace(curr_tok, "")


            prev_was_deleted = prev_tok.tokenIndex in self.deleted_token_indices
            indent_already_emitted = last_kept_tok.type == getattr(
                Python3Parser, "INDENT", -999
            )

            if not (prev_was_deleted and indent_already_emitted):
                gap = self.source_text[prev_tok.stop + 1 : curr_tok.start]
                if gap:
                    clean_gap = re.sub(r"#[^\r\n]*", "", gap)

                    clean_gap = re.sub(r"[ \t]+(?=\r?\n)", "", clean_gap)
                    if clean_gap:
                        self.canon_rewriter.insertBeforeToken(curr_tok, clean_gap)

            last_kept_tok = curr_tok

        result = self.canon_rewriter.getDefaultText()

        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip() + "\n"

    def render_annotated_code(self) -> str:
        """
        Reconstruye el código original conservando formato y comentarios,
        incluyendo las alertas insertadas mediante annot_rewriter.
        """
        tokens = self.token_stream.tokens
        if not tokens:
            return ""

        synthetic_types = {
            getattr(Python3Parser, "INDENT", -999),
            getattr(Python3Parser, "DEDENT", -999),
        }
        annot_replaced: Set[int] = set()

        if tokens[0].type in synthetic_types:
            annot_replaced.add(tokens[0].tokenIndex)
            self.annot_rewriter.replaceSingleToken(tokens[0], "")

        for i in range(1, len(tokens)):
            curr_tok = tokens[i]
            prev_tok = tokens[i - 1]
            if curr_tok.type == Token.EOF:
                break
            if (
                curr_tok.type in synthetic_types
                and curr_tok.tokenIndex not in annot_replaced
            ):
                annot_replaced.add(curr_tok.tokenIndex)
                self.annot_rewriter.replaceSingleToken(curr_tok, "")

            gap = self.source_text[prev_tok.stop + 1 : curr_tok.start]
            if gap:
                self.annot_rewriter.insertBeforeToken(curr_tok, gap)

        return self.annot_rewriter.getDefaultText()


def extract_ngrams(tokens: List[str], k: int = 5) -> Set[Tuple[str, ...]]:
    """
    Genera el conjunto de k-shingles (n-gramas consecutivos de longitud k)
    a partir de la secuencia normalizada de tokens de una función.
    """
    if not tokens:
        return set()
    if len(tokens) < k:
        return {tuple(tokens)}
    return {tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard_similarity(set_a: Set[Tuple[str, ...]], set_b: Set[Tuple[str, ...]]) -> float:
    """
    Calcula el coeficiente de similitud de Jaccard J(A, B) = |A ∩ B| / |A ∪ B|
    expresado en porcentaje (0.0 a 100.0).
    """
    if not set_a and not set_b:
        return 100.0
    union = set_a | set_b
    if not union:
        return 0.0
    intersection = set_a & set_b
    return (len(intersection) / len(union)) * 100.0


def parse_python_source(
    source_text: str, label: str = "<memoria>"
) -> Tuple[PlagiarismListener, str]:
    """Ejecuta el Lexer, Parser y PlagiarismListener de ANTLR v4 sobre código en memoria."""

    if not source_text.endswith("\n"):
        source_text += "\n"

    input_stream = InputStream(source_text)
    error_listener = SyntaxErrorCollector()

    lexer = Python3Lexer(input_stream)
    lexer.removeErrorListeners()
    lexer.addErrorListener(error_listener)

    token_stream = CommonTokenStream(lexer)
    parser = Python3Parser(token_stream)
    parser.removeErrorListeners()
    parser.addErrorListener(error_listener)

    tree = parser.file_input()
    if error_listener.errors:
        joined_errors = "\n  ".join(error_listener.errors[:5])
        raise SyntaxError(f"Errores sintácticos en '{label}':\n  {joined_errors}")

    listener = PlagiarismListener(token_stream, source_text)
    walker = ParseTreeWalker()
    walker.walk(listener, tree)

    return listener, source_text


def parse_python_file(filepath: str) -> Tuple[PlagiarismListener, str]:
    """Ejecuta el Lexer, Parser y PlagiarismListener de ANTLR v4 sobre un archivo."""
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"No se encontró el archivo: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        source_text = f.read()

    return parse_python_source(source_text, label=filepath)


def get_sample_codes() -> Dict[str, str]:
    """Retorna los 3 códigos de ejemplo listos para pruebas por CLI o interfaz web."""
    original_code = '''# Archivo original de referencia (Solucion del estudiante A)
def busqueda_binaria(lista_ordenada, objetivo):
    izquierda = 0
    derecha = len(lista_ordenada) - 1
    while izquierda <= derecha:
        medio = (izquierda + derecha) // 2
        if lista_ordenada[medio] == objetivo:
            return medio
        elif lista_ordenada[medio] < objetivo:
            izquierda = medio + 1
        else:
            derecha = medio - 1
    return -1


def calcular_promedio_pares(numeros):
    suma_total = 0
    cantidad = 0
    for num in numeros:
        if num % 2 == 0:
            suma_total = suma_total + num
            cantidad = cantidad + 1
    if cantidad == 0:
        return 0
    return suma_total / cantidad
'''

    camouflaged_code = '''# Entrega sospechosa (Variables renombradas, comentarios alterados y codigo muerto)
def encontrar_elemento(arreglo, valor_buscado):
    variable_basura_1 = 99999
    inicio = 0
    fin = len(arreglo) - 1
    bandera_falsa = "ignorar_esto"
    while inicio <= fin:
        pivote = (inicio + fin) // 2
        if arreglo[pivote] == valor_buscado:
            return pivote
        elif arreglo[pivote] < valor_buscado:
            inicio = pivote + 1
        else:
            fin = pivote - 1
    return -1


def promedio_elementos_pares(datos_entrada):
    debug_counter = 0
    acumulador = 0
    conteo = 0
    for item in datos_entrada:
        if item % 2 == 0:
            acumulador = acumulador + item
            conteo = conteo + 1
    if conteo == 0:
        return 0
    return acumulador / conteo
'''

    independent_code = '''# Implementacion independiente con enfoque recursivo y comprension de listas
def buscar_recursivo(arr, target, low=0, high=None):
    if high is None:
        high = len(arr) - 1
    if low > high:
        return -1
    mid = (low + high) // 2
    if arr[mid] == target:
        return mid
    if arr[mid] > target:
        return buscar_recursivo(arr, target, low, mid - 1)
    return buscar_recursivo(arr, target, mid + 1, high)


def media_pares_funcional(valores):
    pares = [v for v in valores if v % 2 == 0]
    return sum(pares) / len(pares) if pares else 0
'''

    return {
        "entrada_original.py": original_code,
        "entrada_plagio_camuflado.py": camouflaged_code,
        "entrada_independiente.py": independent_code,
    }


def create_sample_files(base_dir: str = "ejemplos") -> None:
    """Genera los 3 archivos de prueba recomendados para la demostración."""
    os.makedirs(base_dir, exist_ok=True)
    for filename, content in get_sample_codes().items():
        path = os.path.join(base_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Archivo de prueba creado: {path}")


def analyze_code_strings(
    base_source: str,
    suspect_source: str,
    base_label: str = "base.py",
    suspect_label: str = "sospechoso.py",
    threshold: float = 70.0,
    ngram_size: int = 5,
) -> Dict[str, object]:
    """
    Ejecuta el análisis completo en memoria y retorna resultados estructurados
    consumibles tanto por la CLI como por la interfaz gráfica Streamlit.
    """
    base_listener, _ = parse_python_source(base_source, label=base_label)
    suspect_listener, clean_suspect_source = parse_python_source(
        suspect_source, label=suspect_label
    )

    function_results = []
    plagiarism_detected = False
    max_similarity = 0.0
    total_dead_vars = 0

    for s_func in suspect_listener.analyzed_functions:
        s_ngrams = extract_ngrams(s_func.normalized_tokens, k=ngram_size)
        best_score = 0.0
        best_match_name = "N/A"

        for b_func in base_listener.analyzed_functions:
            b_ngrams = extract_ngrams(b_func.normalized_tokens, k=ngram_size)
            score = jaccard_similarity(s_ngrams, b_ngrams)
            if score >= best_score:
                best_score = score
                best_match_name = b_func.original_name

        is_plagiarism = (
            len(base_listener.analyzed_functions) > 0 and best_score >= threshold
        )
        if is_plagiarism:
            plagiarism_detected = True
            suspect_listener.annotate_plagiarism(s_func, best_score, best_match_name)

        max_similarity = max(max_similarity, best_score)
        total_dead_vars += len(s_func.dead_variables)


        symbol_rows = [
            {
                "Identificador Original": sym.original_name,
                "Rol Semántico": sym.role,
                "ID Normalizado": sym.normalized_id,
                "Usos (Def-Use)": sym.uses,
                "Estado": "Código muerto (Eliminado)"
                if (sym.role == "LOCAL" and sym.uses == 0)
                else "Activo",
            }
            for sym in s_func.symbols.values()
        ]

        function_results.append(
            {
                "suspect_func": s_func.original_name,
                "start_line": s_func.start_line,
                "matched_func": best_match_name,
                "similarity": best_score,
                "is_plagiarism": is_plagiarism,
                "dead_variables": list(s_func.dead_variables),
                "normalized_tokens": list(s_func.normalized_tokens),
                "symbols": symbol_rows,
            }
        )

    return {
        "base_functions_count": len(base_listener.analyzed_functions),
        "suspect_functions_count": len(suspect_listener.analyzed_functions),
        "plagiarism_detected": plagiarism_detected,
        "max_similarity": max_similarity,
        "total_dead_vars": total_dead_vars,
        "function_results": function_results,
        "original_suspect_code": clean_suspect_source,
        "canonized_code": suspect_listener.render_canonized_code(),
        "annotated_code": suspect_listener.render_annotated_code(),
    }


def run_plagiarism_analysis(
    base_file: str,
    suspect_file: str,
    threshold: float = 70.0,
    ngram_size: int = 5,
    output_dir: str = os.path.join("ejemplos", "salidas"),
) -> None:
    """Ejecuta la comparación completa y genera los archivos manipulados."""
    print("=" * 72)
    print("  CodeGuard-Py | Análisis y Manipulación Automática de Código (ANTLR v4)")
    print("=" * 72)
    print(f"  Archivo base       : {base_file}")
    print(f"  Archivo sospechoso : {suspect_file}")
    print(f"  Umbral de alerta   : {threshold:.1f}%  |  Tamaño n-gramas: {ngram_size}")
    print("-" * 72)

    base_listener, _ = parse_python_file(base_file)
    suspect_listener, _ = parse_python_file(suspect_file)

    if not base_listener.analyzed_functions or not suspect_listener.analyzed_functions:
        print("[AVISO] Alguno de los archivos no contiene definiciones de funciones ('def').")
        return

    plagiarism_detected = False

    for s_func in suspect_listener.analyzed_functions:
        s_ngrams = extract_ngrams(s_func.normalized_tokens, k=ngram_size)
        best_score = 0.0
        best_match_name = "N/A"

        for b_func in base_listener.analyzed_functions:
            b_ngrams = extract_ngrams(b_func.normalized_tokens, k=ngram_size)
            score = jaccard_similarity(s_ngrams, b_ngrams)
            if score >= best_score:
                best_score = score
                best_match_name = b_func.original_name

        is_plagiarism = best_score >= threshold
        status_label = "ALERTA DE PLAGIO" if is_plagiarism else "SIN PLAGIO"

        print(f"\n  Función analizada : {s_func.original_name}() [Línea {s_func.start_line}]")
        print(f"  Mejor coincidencia: {best_match_name}()")
        print(f"  Similitud Jaccard : {best_score:.2f}%  --> [{status_label}]")
        if s_func.dead_variables:
            print(
                f"  Código muerto     : Eliminadas {len(s_func.dead_variables)} variable(s) "
                f"no usadas: {', '.join(s_func.dead_variables)}"
            )
        else:
            print("  Código muerto     : Ninguna variable sin usar detectada.")

        if is_plagiarism:
            plagiarism_detected = True
            suspect_listener.annotate_plagiarism(s_func, best_score, best_match_name)


    os.makedirs(output_dir, exist_ok=True)
    suspect_basename = os.path.basename(suspect_file)

    canon_path = os.path.join(output_dir, f"canonizado_{suspect_basename}")
    annot_path = os.path.join(output_dir, f"anotado_{suspect_basename}")

    with open(canon_path, "w", encoding="utf-8") as f:
        f.write(suspect_listener.render_canonized_code())

    with open(annot_path, "w", encoding="utf-8") as f:
        f.write(suspect_listener.render_annotated_code())

    print("\n" + "-" * 72)
    print(f"  [SALIDA 1 - Canonizado y depurado]: {canon_path}")
    print(f"  [SALIDA 2 - Código anotado]       : {annot_path}")
    if not plagiarism_detected:
        print("  Resultado global: No se detectaron bloques por encima del umbral.")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CodeGuard-Py: Detector de plagio en Python 3 usando ANTLR v4."
    )
    parser.add_argument(
        "archivo_base",
        nargs="?",
        help="Ruta al archivo Python 3 original de referencia.",
    )
    parser.add_argument(
        "archivo_sospechoso",
        nargs="?",
        help="Ruta al archivo Python 3 a evaluar y manipular.",
    )
    parser.add_argument(
        "--umbral",
        type=float,
        default=70.0,
        help="Porcentaje mínimo de similitud para marcar plagio (por defecto: 70.0).",
    )
    parser.add_argument(
        "--ngramas",
        type=int,
        default=5,
        help="Tamaño k de los n-gramas estructurales (por defecto: 5).",
    )
    parser.add_argument(
        "--crear-ejemplos",
        action="store_true",
        help="Genera los 3 archivos de prueba en la carpeta 'ejemplos/'.",
    )

    args = parser.parse_args()

    try:
        if args.crear_ejemplos:
            create_sample_files()
            return

        if not args.archivo_base or not args.archivo_sospechoso:
            parser.print_help()
            sys.exit(1)

        run_plagiarism_analysis(
            base_file=args.archivo_base,
            suspect_file=args.archivo_sospechoso,
            threshold=args.umbral,
            ngram_size=args.ngramas,
        )
    except (FileNotFoundError, SyntaxError) as err:
        sys.stderr.write(f"\n[ERROR] {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()