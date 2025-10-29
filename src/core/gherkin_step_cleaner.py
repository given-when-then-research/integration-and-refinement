import json
import re
import os
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import logging

"""
GherkinStepCleaner (melhorado)
- Extração mais robusta para Java/Kotlin/Scala (JVM), Ruby, JavaScript/TypeScript/Node.js
- Tratamento de comentários de bloco /* ... */ e strings (mantendo alinhamento de linhas)
- Extração avançada para Node.js/TS com aspas aninhadas e template literals
- Melhor detecção de limites de método (assinaturas multilinha, anotações comentadas)
- Normalização e unescape mais seguros
- Logging detalhado e estatísticas
- Proteções contra entradas None/vazias
- Remove_excess_steps protege contra sobreposição de ranges e preserva formato quando possível
"""

class GherkinStepCleaner:
    """
    Remove métodos de step definitions excessivos de arquivos de teste Gherkin.
    Suporta: Java, Kotlin, Scala, Ruby, JavaScript, TypeScript, Node.js
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir or "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        self.setup_logging()
        self._setup_patterns()
        self.logger.info("GherkinStepCleaner inicializado")
        self.logger.info(f"Linguagens suportadas: {', '.join(self.get_supported_languages())}")
        self.logger.info(f"Diretório de logs: {os.path.abspath(self.log_dir)}")

    def _setup_patterns(self):
        """Configura padrões de regex para cada linguagem"""
        # Helpers para conteúdos entre aspas
        dq_content = r'(?:\\.|[^"\\])*'
        sq_content = r"(?:\\.|[^'\\])*"
        bt_content = r'(?:\\.|[^`\\])*'

        step_str_dq = rf'"({dq_content})"'
        step_str_sq = rf"'({sq_content})'"
        step_str_bt = rf'`({bt_content})`'

        self.patterns = {
            'java': {
                'step_annotation': rf'@(Given|When|Then|And|But)\s*\(\s*(?:{step_str_dq}|{step_str_sq})\s*\)',
                'language_family': 'jvm'
            },
            'kotlin': {
                'step_annotation': rf'@(Given|When|Then|And|But)\s*\(\s*(?:{step_str_dq}|{step_str_sq}|{step_str_bt})\s*\)',
                'language_family': 'jvm'
            },
            'scala': {
                'step_annotation': rf'@(Given|When|Then|And|But)\s*\(\s*(?:{step_str_dq}|{step_str_sq})\s*\)',
                'language_family': 'jvm'
            },
            'ruby': {
                # Ruby pode usar Given / 'text' do OR Given 'text' do OR regex
                'step_annotation': rf'\b(Given|When|Then|And|But)\b\s*(?:\(?\s*(?:/([^/]+)/|{step_str_dq}|{step_str_sq}|{step_str_bt})\s*\)?\s*(?:do|\{{)?)',
                'language_family': 'ruby'
            },
            'javascript': {
                'step_annotation': rf'\b(Given|When|Then|And|But|defineStep)\s*\(\s*(?:{step_str_dq}|{step_str_sq}|{step_str_bt}|/([^/]+)/)',
                'language_family': 'js'
            },
            'typescript': {
                'step_annotation': rf'\b(Given|When|Then|And|But|defineStep)\s*\(\s*(?:{step_str_dq}|{step_str_sq}|{step_str_bt}|/([^/]+)/)',
                'language_family': 'js'
            },
            'nodejs': {
                'step_annotation': rf'\b(Given|When|Then|And|But|defineStep)\s*\(\s*(?:{step_str_dq}|{step_str_sq}|{step_str_bt}|/([^/]+)/)',
                'language_family': 'js'
            }
        }

    def get_supported_languages(self) -> List[str]:
        """Retorna lista de linguagens suportadas"""
        return list(self.patterns.keys())

    def setup_logging(self):
        """Configura sistema de logging"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        main_log_file = os.path.join(self.log_dir, f"gherkin_cleaner_{timestamp}.log")
        self.logger = logging.getLogger(f"GherkinStepCleaner.{timestamp}")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            fh = logging.FileHandler(main_log_file, encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)

    # -----------------------------
    # Utilities for masking content
    # -----------------------------
    def _mask_block_comments_and_strings(self, content: str) -> str:
        """
        Retorna uma version de 'content' onde conteúdo de strings e comentários de bloco
        foi substituído por espaços preservando quebras de linha e comprimento de cada linha.
        Isso permite localizar anotações sem confundir strings/comentários, mantendo indices de linha.
        """
        if content is None:
            return ""

        # Remove CR for consistent handling
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # mask block comments /* ... */ (preserve newlines inside)
        def _block_repl(m):
            s = m.group(0)
            return re.sub(r'[^\n]', ' ', s)  # preserve newlines
        content = re.sub(r'/\*.*?\*/', _block_repl, content, flags=re.DOTALL)

        # mask single line comments //...
        content = re.sub(r'//.*?$', lambda m: ' ' * len(m.group(0)), content, flags=re.MULTILINE)

        # mask strings '...', "..." and `...` (including escapes) preserving newlines
        def _string_repl(m):
            s = m.group(0)
            return re.sub(r'[^\n]', ' ', s)
        content = re.sub(r'"(?:\\.|[^"\\])*"', _string_repl, content)
        content = re.sub(r"'(?:\\.|[^'\\])*'", _string_repl, content)
        content = re.sub(r'`(?:\\.|[^`\\])*`', _string_repl, content)

        return content

    # -----------------------------
    # Unescape & normalization
    # -----------------------------
    def safe_unescape_backslash(self, text: str) -> str:
        if text is None:
            return ""
        result = text
        # common escapes
        replacements = [
            (r'\\n', ' '), (r'\\t', ' '), (r'\\r', ''),
            (r'\\u0022', '"'), (r'\\u0027', "'"), (r'\\u0060', '`'),
        ]
        for a, b in replacements:
            result = result.replace(a, b)
        # remove backslash escapes like \" \' \`
        result = result.replace(r'\"', '"').replace(r"\'", "'").replace(r'\`', '`')
        # collapse double backslashes first
        result = result.replace('\\\\', '\\')
        # strip remaining backslash before alphanum
        result = re.sub(r'\\([A-Za-z0-9_])', r'\1', result)
        return result

    def normalize_step_text(self, step_text: str) -> str:
        """Normaliza texto do step para comparação"""
        if not step_text:
            return ""
        s = step_text
        s = self.safe_unescape_backslash(s)
        # replace parameter-like groups with placeholder
        s = re.sub(r'\{[^}]+\}', '{param}', s)
        s = re.sub(r'\([^)]*\)', '{param}', s)
        s = re.sub(r'\\[wdsWDs]\+?', '{param}', s)
        s = re.sub(r'\.\*', '{param}', s)
        # strip punctuation that isn't meaningful but keep basic punctuation
        s = re.sub(r'[^\w\s\{\}\-\/:;.,]', '', s)
        s = re.sub(r'\s+', ' ', s).strip().lower()
        return s

    # -----------------------------
    # Node.js advanced extraction
    # -----------------------------
    def extract_nodejs_step_definitions_advanced(self, content: str) -> List[str]:
        """
        Extração avançada para Node.js/TypeScript com tratamento de aspas aninhadas.
        Remove comentários primeiro e usa regex tolerante com escapes.
        """
        if not content:
            return []

        # Remove block comments and single-line comments for extraction
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        content_clean = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), content, flags=re.DOTALL)
        content_clean = re.sub(r'//.*?$', lambda m: ' ' * len(m.group(0)), content_clean, flags=re.MULTILINE)

        step_defs = []
        keywords = ['Given', 'When', 'Then', 'And', 'But', 'defineStep']

        # Pattern for 'keyword( '...' , ' or )'
        for keyword in keywords:
            # capture quoted strings with proper escaping handling
            pattern = rf'\b{keyword}\s*\(\s*(["\'])(?P<body>(?:(?:(?!\1).)|\\.)*?)\1\s*[,)\n]'
            for m in re.finditer(pattern, content_clean, flags=re.DOTALL):
                body = m.group('body') or ''
                body = self.safe_unescape_backslash(body)
                step_defs.append(body)

        # template literals/backticks
        for m in re.finditer(r'\b(?:Given|When|Then|And|But|defineStep)\s*\(\s*`(?P<body>[^`]*)`', content_clean, flags=re.DOTALL):
            body = m.group('body') or ''
            step_defs.append(body)

        # regex literals
        for m in re.finditer(r'\b(?:Given|When|Then|And|But|defineStep)\s*\(\s*/(?P<body>[^/]+)/[gimuy]*', content_clean):
            body = m.group('body') or ''
            step_defs.append(body)

        return [self.safe_unescape_backslash(sd).strip() for sd in step_defs]

    # -----------------------------
    # Method boundary finders
    # -----------------------------
    def find_method_boundaries_jvm(self, lines: List[str], annotation_line: int, language: str, is_commented: bool = False) -> Tuple[int, int]:
        """
        Encontra limites de método para Java/Kotlin/Scala (JVM)
        - Suporta assinatura multilinha e modificadores em linhas anteriores.
        - annotation_line is the line where the annotation was detected (0-based).
        """
        n = len(lines)
        # start searching from the annotation line forward to find the opening '{' of the method body
        sig_start = None
        brace_balance = 0
        max_search = 200  # mais permissivo
        # attempt to find the first line that looks like part of method signature (contains '(' )
        for j in range(annotation_line + 1, min(n, annotation_line + 1 + max_search)):
            line = lines[j]
            if not line.strip():
                continue
            # ignore other annotations on consecutive lines
            if line.strip().startswith('@'):
                continue
            # If line contains '(' consider it's signature start
            if '(' in line:
                sig_start = j
                # From sig_start, search until we find an opening brace '{' and then match closing brace.
                for k in range(sig_start, min(n, sig_start + max_search)):
                    current = lines[k]
                    # Count braces but ignore braces inside quotes naive approach: remove quoted parts
                    tmp = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', current)
                    brace_balance += tmp.count('{') - tmp.count('}')
                    if '{' in tmp:
                        # found start of body; now find matching closing brace
                        if brace_balance <= 0:
                            return sig_start, k
                        for m in range(k + 1, n):
                            cur2 = lines[m]
                            tmp2 = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', cur2)
                            brace_balance += tmp2.count('{') - tmp2.count('}')
                            if brace_balance <= 0:
                                return sig_start, m
                        return -1, -1
                break

        # fallback: try to find a block starting with '{' after annotation_line
        for j in range(annotation_line + 1, min(n, annotation_line + 1 + max_search)):
            if '{' in lines[j]:
                # find matching brace
                brace_balance = lines[j].count('{') - lines[j].count('}')
                for k in range(j + 1, n):
                    brace_balance += lines[k].count('{') - lines[k].count('}')
                    if brace_balance <= 0:
                        # choose method_start as annotation_line+1 (best-effort)
                        method_start_line = annotation_line + 1
                        return method_start_line, k
                return -1, -1

        return -1, -1

    def find_method_boundaries_ruby(self, lines: List[str], annotation_line: int) -> Tuple[int, int]:
        """
        Encontra limites de método para Ruby: suporta 'do...end' e '{...}'.
        """
        n = len(lines)
        method_start = annotation_line
        # procurar 'do' ou '{' nas próximas linhas (até um limite)
        for j in range(annotation_line, min(n, annotation_line + 10)):
            line = lines[j]
            if ' do' in line or line.strip().endswith('do') or line.strip().startswith('do'):
                # find matching 'end'
                depth = 0
                for k in range(j, n):
                    cur = lines[k]
                    # count do and end occurrences na forma simples (heurística)
                    depth += len(re.findall(r'\bdo\b', cur)) - len(re.findall(r'\bend\b', cur))
                    if depth <= 0 and re.search(r'\bend\b', cur):
                        return method_start, k
                return -1, -1
            if '{' in line:
                brace_balance = line.count('{') - line.count('}')
                if brace_balance <= 0:
                    return method_start, j
                for k in range(j + 1, n):
                    brace_balance += lines[k].count('{') - lines[k].count('}')
                    if brace_balance <= 0:
                        return method_start, k
                return -1, -1
        return -1, -1

    def find_method_boundaries_js(self, lines: List[str], annotation_line: int) -> Tuple[int, int]:
        """
        Encontra limites de função para JS/TS: () => { ... }, function ... { ... }
        """
        n = len(lines)
        method_start = annotation_line
        brace_balance = 0
        found_start = False
        max_search = 200
        for j in range(annotation_line, min(n, annotation_line + max_search)):
            line = lines[j]
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue
            if 'function' in stripped or '=>' in stripped or 'async' in stripped:
                found_start = True
            if '{' in stripped:
                brace_balance += stripped.count('{') - stripped.count('}')
                if brace_balance <= 0:
                    return method_start, j
                for k in range(j + 1, n):
                    brace_balance += lines[k].count('{') - lines[k].count('}')
                    if brace_balance <= 0:
                        return method_start, k
                return -1, -1
        return -1, -1

    def find_method_boundaries(self, lines: List[str], annotation_line: int, language: str, is_commented: bool = False) -> Tuple[int, int]:
        """
        Dispatcher para família de linguagens
        """
        if language not in self.patterns:
            return -1, -1
        fam = self.patterns[language].get('language_family', 'unknown')
        if fam == 'jvm':
            return self.find_method_boundaries_jvm(lines, annotation_line, language, is_commented)
        if fam == 'ruby':
            return self.find_method_boundaries_ruby(lines, annotation_line)
        if fam == 'js':
            return self.find_method_boundaries_js(lines, annotation_line)
        return -1, -1

    # -----------------------------
    # Main extraction logic
    # -----------------------------
    def extract_step_definitions(self, code: str, language: str) -> List[Dict]:
        """
        Extrai step definitions do código, retornando uma lista com:
        { step_type, step_text, normalized_step, annotation_line, start_line, end_line, is_commented }
        """
        if not code:
            return []

        language = language.lower()
        if language not in self.patterns:
            return []

        # Prepare lines and masked content to avoid matching inside strings or block comments
        lines = code.replace('\r\n', '\n').replace('\r', '\n').splitlines()
        masked = self._mask_block_comments_and_strings(code)
        masked_lines = masked.splitlines()

        patt = self.patterns[language]['step_annotation']
        extracted = []
        n = len(lines)

        for i in range(len(masked_lines)):
            line = masked_lines[i]
            try:
                m = re.search(patt, line)
            except re.error:
                self.logger.error(f"Regex error for pattern on line {i}: {patt}")
                continue
            if not m:
                continue

            # determine if original line was commented (for JVM comments like //)
            original_line = lines[i] if i < n else ''
            is_commented = original_line.strip().startswith('//')

            step_type = None
            # first capture group should be step type in our patterns
            try:
                step_type = m.group(1)
            except Exception:
                step_type = m.group(1) if m.groups() else None

            # extract step text from several possible capture groups (choose first non-empty)
            step_text = None
            for gi in range(2, (m.lastindex or 1) + 1):
                try:
                    g = m.group(gi)
                except Exception:
                    g = None
                if g:
                    step_text = g
                    break

            # fallback: try to capture quoted content in the original line if nothing found
            if step_text is None:
                qmatch = re.search(r'["\'`]\s*(?P<body>(?:\\.|[^"\'`\\])*)\s*["\'`]', original_line)
                if qmatch:
                    step_text = qmatch.group('body')

            if step_text is None:
                self.logger.debug(f"Não foi possível extrair texto do step na linha {i}: {original_line!r}")
                continue

            # find method boundaries using original lines (not masked) to keep indexes correct
            start_line, end_line = self.find_method_boundaries(lines, i, language, is_commented)

            if start_line != -1 and end_line != -1:
                actual_start = min(i, start_line) if is_commented else start_line
                extracted.append({
                    'step_type': step_type,
                    'step_text': step_text,
                    'normalized_step': self.normalize_step_text(step_text),
                    'annotation_line': i,
                    'start_line': actual_start,
                    'end_line': end_line,
                    'is_commented': is_commented
                })
            else:
                self.logger.warning(f"Não encontrou método correspondente para step '{step_text}' (linha {i})")

        self.logger.debug(f"Extraídos {len(extracted)} step definitions ({language})")
        return extracted

    # -----------------------------
    # Remove excess steps
    # -----------------------------
    def remove_excess_steps(self, code: str, language: str, excess_steps: List[List[str]]) -> Tuple[str, List[str], List[List[str]]]:
        """
        Remove step definitions excedentes do código.
        - excess_steps: lista de pares [tipo, texto] (como vindo do analisador)
        Retorna: (cleaned_code, removed_methods_list, remaining_excess_steps)
        """
        if language is None:
            raise ValueError("Linguagem é None")
        lang = language.lower()
        if lang not in self.patterns:
            raise ValueError(f"Linguagem não suportada: {language}")

        if code is None:
            return "", [], excess_steps or []

        lines = code.replace('\r\n', '\n').replace('\r', '\n').splitlines()
        original_line_count = len(lines)
        if original_line_count == 0:
            return code, [], excess_steps or []

        # Extract defs
        step_defs = self.extract_step_definitions(code, lang)

        # build set of normalized excess texts for quick lookup
        normalized_excess = {}
        if excess_steps:
            for es in excess_steps:
                # es can be [type, text] or just text
                try:
                    txt = es[1] if isinstance(es, (list, tuple)) and len(es) > 1 else (es if isinstance(es, str) else str(es))
                except Exception:
                    txt = str(es)
                norm = self.normalize_step_text(txt)
                normalized_excess.setdefault(norm, []).append(txt)

        lines_to_remove = set()
        removed_methods = []
        removed_excess_originals = []

        for sd in step_defs:
            norm = sd.get('normalized_step') or self.normalize_step_text(sd.get('step_text'))
            if norm in normalized_excess:
                # mark lines for removal from start to end inclusive
                s = sd['start_line']
                e = sd['end_line']
                if s is None or e is None or s < 0 or e < 0:
                    # skip if invalid boundaries
                    self.logger.warning(f"Ignorando step com limites inválidos: {sd}")
                    continue
                for i in range(s, e + 1):
                    lines_to_remove.add(i)
                removed_methods.append(f"{sd.get('step_type')}: \"{sd.get('step_text')}\"")
                # pick one original excess text as removed for bookkeeping (pop-style)
                originals = normalized_excess.get(norm)
                if originals:
                    removed_excess_originals.append(originals.pop(0))
                self.logger.info(f"  MARCADO PARA REMOÇÃO: {sd.get('step_type')}: \"{sd.get('step_text')}\" (linhas {s}-{e})")
            else:
                self.logger.debug(f"  MANTIDO: {sd.get('step_type')}: \"{sd.get('step_text')}\"")

        # If nothing to remove, return original
        if not lines_to_remove:
            self.logger.info("Nenhuma linha marcada para remoção.")
            return code, [], excess_steps or []

        # Create cleaned lines preserving lines not removed
        cleaned_lines = [line for idx, line in enumerate(lines) if idx not in lines_to_remove]

        # Heurística: se remoção deixou múltiplas quebras de linha, colapsar múltiplas vazias
        cleaned_code = "\n".join(cleaned_lines)
        cleaned_code = re.sub(r'\n{3,}', '\n\n', cleaned_code).strip()

        # Preserve final newline if original had
        if code.endswith('\n') and cleaned_code and not cleaned_code.endswith('\n'):
            cleaned_code += '\n'

        # remaining excess steps: filter originals list by those not removed (if same structure)
        remaining_excess = []
        if excess_steps:
            # build a normalized set of removed originals
            removed_norms = set(self.normalize_step_text(x) for x in removed_excess_originals)
            for es in excess_steps:
                try:
                    txt = es[1] if isinstance(es, (list, tuple)) and len(es) > 1 else (es if isinstance(es, str) else str(es))
                except Exception:
                    txt = str(es)
                if self.normalize_step_text(txt) not in removed_norms:
                    remaining_excess.append(es)
        else:
            remaining_excess = []

        self.logger.info(f"Linhas removidas: {original_line_count - len(cleaned_code.splitlines()) if cleaned_code else original_line_count}")
        self.logger.info(f"Métodos removidos: {len(removed_methods)}")
        self.logger.info(f"Steps excedentes restantes: {len(remaining_excess)}")

        return cleaned_code, removed_methods, remaining_excess