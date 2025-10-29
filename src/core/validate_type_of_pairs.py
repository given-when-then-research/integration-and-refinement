import os
import json
import re
import sys
from typing import List, Tuple, Dict, Any

# Prefixo regex para identificar palavras-chave Gherkin (Given, When, Then, And, But)
GHERKIN_STEP_PREFIX = r'(Given|When|Then|And|But)'

# Padrões oficiais de step definitions por linguagem (baseado na heurística v4)
STEP_ANNOTATION_PATTERNS = {
    'java': [
        r'@(?:Given|When|Then|And|But)\s*\(\s*"(.+?)"\s*\)',
        r'@(?:Given|When|Then|And|But)\s*\(\s*value\s*=\s*"([^"]+)"\s*\)',
        r'@(?:Given|When|Then|And|But)\s*\(\s*"([^"]+)"\s*,\s*timeout\s*=\s*\d+\s*\)',
    ],
    'kotlin': [
        r'@(?:Given|When|Then|And|But)\s*\(\s*"([^"]+)"\s*\)',
        r'@(?:Given|When|Then|And|But)\s*\(\s*value\s*=\s*"([^"]+)"\s*\)',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*[\'"](.+?)[\'"]\s*\)\s*\{',
    ],
    'nodejs': [
        # CRÍTICO: Extração robusta para Node.js/TypeScript com aspas aninhadas
        # Padrão 1: Aspas simples externas (pode conter aspas duplas internas escapadas ou não)
        r"\b(?:Given|When|Then|And|But)\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        # Padrão 2: Aspas duplas externas (pode conter aspas simples internas escapadas ou não)
        r'\b(?:Given|When|Then|And|But)\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        # Padrão 3: Template literals (backticks)
        r'\b(?:Given|When|Then|And|But)\s*\(\s*`([^`]*)`',
        # Padrão 4: Regex literals
        r'\b(?:Given|When|Then|And|But)\s*\(\s*/([^/]+)/[gimuy]*',
        # Padrão 5: defineStep
        r"\bdefineStep\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        r'\bdefineStep\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        r'\bdefineStep\s*\(\s*`([^`]*)`',
        r'\bdefineStep\s*\(\s*/([^/]+)/[gimuy]*',
    ],
    'javascript': [
        r"\b(?:Given|When|Then|And|But)\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        r'\b(?:Given|When|Then|And|But)\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*`([^`]*)`',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*/([^/]+)/[gimuy]*',
        r"\bdefineStep\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        r'\bdefineStep\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        r'\bdefineStep\s*\(\s*`([^`]*)`',
        r'\bdefineStep\s*\(\s*/([^/]+)/[gimuy]*',
    ],
    'typescript': [
        r"\b(?:Given|When|Then|And|But)\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        r'\b(?:Given|When|Then|And|But)\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*`([^`]*)`',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*/([^/]+)/[gimuy]*',
        r"\bdefineStep\s*\(\s*'([^']*(?:\\'[^']*)*)'",
        r'\bdefineStep\s*\(\s*"([^"]*(?:\\"[^"]*)*)"',
        r'\bdefineStep\s*\(\s*`([^`]*)`',
        r'\bdefineStep\s*\(\s*/([^/]+)/[gimuy]*',
    ],
    'ruby': [
        r'\b(?:Given|When|Then|And|But)\s*\(\s*/([^/]+)/\s*\)\s*do',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*\)\s*do',
        r'\b(?:Given|When|Then|And|But)\s*/([^/]+)/\s*do',
        r'\b(?:Given|When|Then|And|But)\s+[\'"`]([^\'"`]+)[\'"`]\s+do',
    ],
    'go': [
        r'\bctx\.Step\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*,',
        r'\bs\.Step\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*,',
        r'\bgodog\.Step\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*,',
    ],
    'cpp': [
        r'\b(?:GIVEN|WHEN|THEN|STEP_GIVEN|STEP_WHEN|STEP_THEN)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*\)',
    ],
    'lua': [
        r'\bstep_definitions\.(?:given|when|then)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*,',
        r'\b(?:Given|When|Then|And|But)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]\s*\)',
    ],
    'ocaml': [
        r'\b(?:step|given|when|then)_[a-z]+\s+~text:\s*[\'"`]([^\'"`]+)[\'"`]',
        r'\blet\s+\w+\s*=\s*(?:step|given|when|then)_[a-z]+\s+~text:\s*[\'"`]([^\'"`]+)[\'"`]',
    ],
    'scala': [
        r'@(?:Given|When|Then|And|But)\s*\(\s*"([^"]+)"\s*\)',
        r'(?:Given|When|Then|And|But)\s*\(\s*"""([^"]+)"""\s*\)',
        r'(?:Given|When|Then|And|But)\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ],
}

# Mapeamento de aliases de linguagem
LANGUAGE_ALIASES = {
    'rb': 'ruby',
    'js': 'javascript',
    'ts': 'typescript',
    'android': 'java',
    'golang': 'go',
    'c++': 'cpp',
    'cxx': 'cpp',
    'ml': 'ocaml',
}


def get_language_canonical(language: str) -> str:
    """Obtém nome canônico da linguagem."""
    lang = language.lower().strip()
    return LANGUAGE_ALIASES.get(lang, lang)


def extract_background_steps(feature_content: str) -> List[Tuple[str, str]]:
    """
    NOVA FUNÇÃO: Extrai APENAS os steps do Background para referência.
    Melhorias:
    - Suporta título na mesma linha: "Background: Title"
    - Mais tolerante com indentação
    """
    if not feature_content:
        return []

    # Encontra o bloco Background (suporta título na mesma linha)
    background_match = re.search(
        r'^\s*Background\b[^\n]*\n(.*?)(?=^\s*(?:Scenario(?:\s+Outline)?|Feature|Rule|@|\Z))',
        feature_content,
        flags=re.MULTILINE | re.DOTALL
    )

    if not background_match:
        return []

    background_block = background_match.group(1)

    # Extrai steps do Background (captura tipo e texto)
    steps = re.findall(
        rf'^\s*{GHERKIN_STEP_PREFIX}\s+(.*?)\s*$',
        background_block,
        re.MULTILINE
    )

    return [(step_type.strip(), step_text.strip()) for step_type, step_text in steps]


def extract_gherkin_steps(feature_content: str) -> List[Tuple[str, str]]:
    """
    Extrai passos de arquivos .feature (Gherkin), EXCLUINDO steps do Background.
    Melhorias:
    - Remove o bloco Background mais robustamente (título na mesma linha, indentação)
    - Mantém extração de tipo e texto do step
    """
    if not feature_content:
        return []

    # Remove Background de forma mais robusta (suporta título na mesma linha)
    feature_no_background = re.sub(
        r'^\s*Background\b[^\n]*\n.*?(?=^\s*(?:Scenario(?:\s+Outline)?|Feature|Rule|@|\Z))',
        '',
        feature_content,
        flags=re.MULTILINE | re.DOTALL
    )

    # Extrai steps mantendo contexto (captura tipo e texto)
    steps = re.findall(
        rf'^\s*{GHERKIN_STEP_PREFIX}\s+(.*?)\s*$',
        feature_no_background,
        re.MULTILINE
    )

    return [(step_type.strip(), step_text.strip()) for step_type, step_text in steps]


def extract_nodejs_step_definitions_advanced(content: str) -> List[str]:
    """
    NOVA FUNÇÃO: Extração avançada para Node.js/TypeScript com tratamento de aspas aninhadas.
    """
    step_defs = []

    # Remove comentários primeiro
    content_clean = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
    content_clean = re.sub(r'/\*.*?\*/', '', content_clean, flags=re.DOTALL)

    # Padrão para encontrar chamadas de step definitions
    # Captura: Given('texto aqui', function)
    keywords = ['Given', 'When', 'Then', 'And', 'But', 'defineStep']

    for keyword in keywords:
        # Procura por padrão: keyword('...' ou "..." ou `...`, seguido de vírgula ou parêntese
        pattern = rf'\b{keyword}\s*\(\s*(["\'])((?:(?!\1).|\\.)*?)\1\s*[,)]'

        matches = re.finditer(pattern, content_clean, re.DOTALL)

        for match in matches:
            quote_type = match.group(1)  # ' ou "
            step_text = match.group(2)    # conteúdo entre aspas

            # Desescapa aspas do mesmo tipo que o delimitador
            if quote_type == "'":
                step_text = step_text.replace("\\'", "'")
            elif quote_type == '"':
                step_text = step_text.replace('\\"', '"')

            step_defs.append(step_text)

    # Trata template literals (backticks) separadamente
    backtick_pattern = r'\b(?:Given|When|Then|And|But|defineStep)\s*\(\s*`([^`]*)`'
    for match in re.finditer(backtick_pattern, content_clean):
        step_defs.append(match.group(1))

    # Trata regex literals
    regex_pattern = r'\b(?:Given|When|Then|And|But|defineStep)\s*\(\s*/([^/]+)/[gimuy]*'
    for match in re.finditer(regex_pattern, content_clean):
        step_defs.append(match.group(1))

    return step_defs


def safe_unescape_backslash(text: str) -> str:
    """
    NOVA FUNÇÃO: Remove escapes de backslash de forma segura e progressiva.
    Trata casos como: \\", \\', \\n, \\t, \\\\, etc.
    """
    result = text
    
    # Ordem importante: do mais específico para o mais geral
    escape_sequences = [
        # 1. Escapes de regex comuns que devem ser preservados em certos contextos
        # mas removidos para comparação
        (r'\\d', 'd'),  # dígito
        (r'\\w', 'w'),  # palavra
        (r'\\s', 's'),  # espaço
        (r'\\D', 'D'),  # não-dígito
        (r'\\W', 'W'),  # não-palavra
        (r'\\S', 'S'),  # não-espaço
        
        # 2. Escapes especiais de string
        (r'\\n', ' '),   # newline -> espaço
        (r'\\t', ' '),   # tab -> espaço
        (r'\\r', ''),    # carriage return -> remove
        
        # 3. Escapes de aspas (múltiplos níveis)
        (r'\\\\"', '"'),   # \\" -> "
        (r'\\\"', '"'),    # \" -> "
        (r"\\\\'", "'"),   # \\' -> '
        (r"\\\'", "'"),    # \' -> '
        (r'\\\\`', '`'),   # \\` -> `
        (r'\\`', '`'),     # \` -> `
        
        # 4. Barras invertidas duplas
        (r'\\\\', '\\'),   # \\\\ -> \\ (primeiro passo)
    ]
    
    for pattern, replacement in escape_sequences:
        result = result.replace(pattern, replacement)
    
    # 5. Segunda passada para pegar \\ restantes
    result = result.replace('\\\\', '\\')
    
    # 6. Remove backslashes isoladas que precedem caracteres normais
    # Mas preserva se for parte de algo importante
    result = re.sub(r'\\([a-zA-Z0-9_])', r'\1', result)
    
    return result


def normalize_escapes_aggressively(text: str) -> str:
    """
    MELHORADA: Normaliza TODAS as formas de escape com tratamento especial para backslash.
    """
    # 1. Primeiro, trata escapes de backslash de forma segura
    result = safe_unescape_backslash(text)
    
    # 2. Trata Unicode escapes
    unicode_escapes = [
        (r'\\u0022', '"'),       # \u0022 -> "
        (r'\\u0027', "'"),       # \u0027 -> '
        (r'\\u0060', '`'),       # \u0060 -> `
        (r'\\u005C', '\\'),      # \u005C -> \
    ]
    
    for pattern, replacement in unicode_escapes:
        result = result.replace(pattern, replacement)
    
    # 3. Trata HTML entities
    html_entities = [
        ('&quot;', '"'),
        ('&apos;', "'"),
        ('&#34;', '"'),
        ('&#39;', "'"),
        ('&grave;', '`'),
        ('&#96;', '`'),
    ]
    
    for entity, replacement in html_entities:
        result = result.replace(entity, replacement)
    
    # 4. Remove qualquer backslash solitária restante antes de aspas
    result = re.sub(r'\\(["\'])', r'\1', result)
    
    return result


def expand_slash_alternatives_in_pattern(text: str) -> str:
    """
    Converte ocorrências do tipo 'a/the' (ou 'foo/bar' quando ambos são palavras simples)
    para '(?:a|the)' — isso permite tratamento regex/alternativa posteriormente.
    Evita transformar caminhos como 'path/to/file' porque exige que ambos os lados sejam palavras curtas.
    """
    def replace_fn(m):
        left = m.group(1)
        right = m.group(2)
        # Proteções: só converte se ambas as partes forem alfabéticas e curtas (<= 10)
        if re.fullmatch(r'[A-Za-z]+', left) and re.fullmatch(r'[A-Za-z]+', right) and len(left) <= 10 and len(right) <= 10:
            return f'(?:{left}|{right})'
        return m.group(0)

    # Procura 'word/word' sem barras adicionais e substitui de forma segura
    return re.sub(r'\b([A-Za-z]+)\/([A-Za-z]+)\b', replace_fn, text)


def generate_slash_variants(text: str) -> List[str]:
    """
    Gera variantes substituindo ocorrências 'word/other' por cada alternativa.
    Exemplo: 'contains a/the single' -> ['contains a single', 'contains the single']
    Trata múltiplas ocorrências por produto cartesiano.
    """
    pattern = re.compile(r'\b([A-Za-z]+)\/([A-Za-z]+)\b')

    # Encontrar todas as ocorrências
    matches = list(pattern.finditer(text))
    if not matches:
        return [text]

    variants = ['']
    last_idx = 0
    for m in matches:
        prefix = text[last_idx:m.start()]
        left, right = m.group(1), m.group(2)
        new_variants = []
        for v in variants:
            new_variants.append(v + prefix + left)
            new_variants.append(v + prefix + right)
        variants = new_variants
        last_idx = m.end()
    suffix = text[last_idx:]
    return [v + suffix for v in variants]


def remove_determiners(text: str) -> str:
    """
    Remove artigos determinantes simples ('a', 'an', 'the') para permitir matching
    quando step definitions usam formas opcionais.
    Só usado em estratégias alternativas para não estragar normalização básica.
    """
    # Remove apenas artigos isolados (mantém os demais conteúdos)
    return re.sub(r'\b(?:a|an|the)\s+', '', text)


def preprocess_step_definition(raw_pattern: str) -> str:
    """
    MELHORADA: Pré-processa step definition removendo TODOS os escapes.
    """
    pattern = raw_pattern.strip()

    # Remove âncoras regex
    if pattern.startswith('^'):
        pattern = pattern[1:]
    if pattern.endswith('$'):
        pattern = pattern[:-1]

    # CRÍTICO: Normaliza escapes de forma agressiva
    pattern = normalize_escapes_aggressively(pattern)

    # Expande alternativas escritas com barra (a/the -> (?:a|the))
    pattern = expand_slash_alternatives_in_pattern(pattern)

    # Normaliza Unicode quotes
    unicode_quotes = [
        ('"', '"'),
        ('"', '"'),
        (''', "'"),
        (''', "'"),
        ('`', '"'),
    ]

    for old, new in unicode_quotes:
        pattern = pattern.replace(old, new)

    return pattern.strip()


def extract_step_definitions_unified(matched_content: str, language: str) -> List[str]:
    """
    Extração robusta com pré-processamento específico para Node.js.
    """
    if not matched_content:
        return []

    canonical_lang = get_language_canonical(language)

    # MELHORIA CRÍTICA: Para Node.js/TS/JS, usa extração avançada
    if canonical_lang in ['nodejs', 'javascript', 'typescript']:
        return [preprocess_step_definition(sd)
                for sd in extract_nodejs_step_definitions_advanced(matched_content)]

    # Para outras linguagens, usa padrões regex tradicionais
    patterns = STEP_ANNOTATION_PATTERNS.get(canonical_lang, [])

    if not patterns:
        patterns = STEP_ANNOTATION_PATTERNS.get('java', [])

    step_defs = []
    for pattern in patterns:
        try:
            matches = re.findall(pattern, matched_content,
                                 re.MULTILINE | re.DOTALL)
            step_defs.extend(matches)
        except re.error:
            continue

    return [preprocess_step_definition(sd) for sd in step_defs]


def normalize_text_for_comparison(text: str) -> str:
    """
    MELHORADA: Normalização uniforme para Gherkin e Step Definitions.
    """
    # 1. Normaliza escapes primeiro (agora com tratamento melhorado de backslash)
    normalized = normalize_escapes_aggressively(text)

    # 2. Normaliza espaços
    normalized = re.sub(r'\s+', ' ', normalized.strip())

    # 3. Normaliza Unicode quotes
    unicode_mappings = [
        ('"', '"'),
        ('"', '"'),
        (''', "'"),
        (''', "'"),
        ('`', '"'),
    ]
    for old, new in unicode_mappings:
        normalized = normalized.replace(old, new)

    # 4. Converte para lowercase
    normalized = normalized.lower()

    return normalized


def normalize_gherkin_step_advanced(step: str) -> str:
    """
    Normalização avançada com placeholders para comparação estrutural.
    """
    # Usa a normalização central
    normalized = normalize_text_for_comparison(step)

    # Substitui padrões por placeholders
    substitutions = [
        # 1. Strings entre aspas (preserva o conteúdo para comparação)
        (r'"[^"]*"', '<STRING>'),
        (r"'[^']*'", '<STRING>'),

        # 2. Números
        (r'\b\d+\.\d+\b', '<NUMBER>'),
        (r'\b\d+\b', '<NUMBER>'),

        # 3. Parâmetros
        (r'<[^>]+>', '<PARAM>'),
        (r'\{[^}]+\}', '<PARAM>'),
        (r'\([^)]*\)', '<PARAM>'),
        (r'\[[^\]]*\]', '<PARAM>'),
    ]

    for pattern, replacement in substitutions:
        normalized = re.sub(pattern, replacement, normalized)

    # Normaliza espaços ao redor de placeholders
    normalized = re.sub(r'\s*<\w+>\s*', ' <PARAM> ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip()


def convert_to_advanced_regex(step_def_normalized: str) -> str:
    """
    Converte step definition para regex avançada.
    """
    pattern = step_def_normalized

    # Substitui padrões de captura por placeholders
    capture_patterns = [
        (r'"?\([^\)]*\)"?', '<<<CAP>>>'),
        (r'\{string\}', '<<<CAP>>>'),
        (r'\{int\}', '<<<CAP>>>'),
        (r'\{float\}', '<<<CAP>>>'),
        (r'\{word\}', '<<<CAP>>>'),
        (r'\{any\}', '<<<CAP>>>'),
        (r'\{[^}]+\}', '<<<CAP>>>'),
    ]

    for cap_pattern, placeholder in capture_patterns:
        pattern = re.sub(cap_pattern, placeholder, pattern)

    # Escapa caracteres especiais
    # Mas se o pattern já contém grupos ou alternações (?:...|...), não escapar tudo:
    contains_regex_construct = bool(re.search(r'[\(\)\|\?\:\[\]]', pattern))
    if not contains_regex_construct:
        pattern = re.escape(pattern)
    else:
        # Escapa apenas alguns caracteres para evitar quebrar construtos já intencionais
        pattern = pattern.replace('\\', '\\\\')
        pattern = re.sub(r'([.+^$])', r'\\\1', pattern)

    # Restaura placeholders
    pattern = pattern.replace('<<<CAP>>>', '.+?')

    # Permite espaços flexíveis
    pattern = re.sub(r'\\ +', r'\\s+', pattern)

    return pattern


def steps_match_advanced(gherkin_step: str, step_def: str) -> Tuple[bool, str]:
    """
    MELHORADA: Match com normalização unificada e tratamento especial de aspas e backslash.
    Inclui novas estratégias:
    - Expansão de alternativas escritas com barra (a/the)
    - Remoção de determiners (a/an/the) como variante
    - Geração de variantes (a/the -> a | the) e comparação
    """
    # Normalização central para ambos
    g_norm = normalize_text_for_comparison(gherkin_step)
    d_norm = normalize_text_for_comparison(step_def)

    # Estratégia 1: Match exato após normalização completa
    if g_norm == d_norm:
        return True, 'exact'

    # Estratégia 2: Match ignorando diferenças entre tipos de aspas
    g_no_quote_diff = re.sub(r'["\']', '§', g_norm)
    d_no_quote_diff = re.sub(r'["\']', '§', d_norm)
    if g_no_quote_diff == d_no_quote_diff:
        return True, 'exact'

    # Estratégia 3: Match ignorando TODAS as aspas completamente
    g_no_quotes = re.sub(r'["\']', '', g_norm)
    d_no_quotes = re.sub(r'["\']', '', d_norm)
    if g_no_quotes == d_no_quotes:
        return True, 'exact'

    # Estratégia 4: Match com aspas normalizadas para um único tipo
    g_unified = g_norm.replace("'", '"')
    d_unified = d_norm.replace("'", '"')
    if g_unified == d_unified:
        return True, 'exact'

    # NOVA Estratégia 5: Expandir alternativas escritas com barra na definição e comparar variantes
    # Ex.: "a/the" -> try both "a" and "the"
    d_variants = generate_slash_variants(step_def)
    for dv in d_variants:
        dv_norm = normalize_text_for_comparison(dv)
        if g_norm == dv_norm:
            return True, 'slash_variant'
        # também tenta sem aspas
        if re.sub(r'["\']', '', g_norm) == re.sub(r'["\']', '', dv_norm):
            return True, 'slash_variant'

    # NOVA Estratégia 6: Remover determiners (a/an/the) como variante (tanto gherkin quanto def)
    g_no_det = remove_determiners(g_norm)
    d_no_det = remove_determiners(d_norm)
    if g_no_det == d_no_det:
        return True, 'no_determiner'
    # Com variantes de slash também
    for dv in d_variants:
        dv_norm = normalize_text_for_comparison(dv)
        if remove_determiners(dv_norm) == g_no_det:
            return True, 'no_determiner'

    # Estratégia 7: Raw Regex (se a definição parecer já ser regex/alternativa)
    try:
        d_raw_regex = step_def
        # Se preprocess deixou '(?:a|the)' ou outras alternações, podemos usar diretamente como regex.
        if not d_raw_regex.startswith('^'):
            d_raw_regex = '^' + d_raw_regex
        if not d_raw_regex.endswith('$'):
            d_raw_regex = d_raw_regex + '$'

        if re.fullmatch(d_raw_regex, g_norm, re.IGNORECASE):
            return True, 'raw_regex'
    except:
        pass

    # Estratégia 8: Normalização avançada com placeholders
    g_advanced = normalize_gherkin_step_advanced(gherkin_step)
    d_advanced = normalize_gherkin_step_advanced(step_def)

    if g_advanced == d_advanced:
        return True, 'normalized'

    # Estratégia 9: Comparação estrutural
    g_skeleton = re.sub(r'<\w+>', '<PARAM>', g_advanced)
    d_skeleton = re.sub(r'<\w+>', '<PARAM>', d_advanced)

    if g_skeleton == d_skeleton:
        return True, 'structural'

    # Estratégia 10: Advanced Regex
    try:
        regex_pattern = convert_to_advanced_regex(step_def)
        if re.fullmatch(regex_pattern, g_norm, re.IGNORECASE):
            return True, 'advanced_regex'
    except:
        pass

    # Estratégia 11: Remove delimitadores completamente
    g_bare = re.sub(r'["\'`<{(\[][^"\'`>})\]]*["\'`>})\]]', ' ', g_norm)
    g_bare = re.sub(r'\s+', ' ', g_bare).strip()

    d_bare = re.sub(r'["\'`<{(\[][^"\'`>})\]]*["\'`>})\]]', ' ', d_norm)
    d_bare = re.sub(r'\s+', ' ', d_bare).strip()

    if g_bare == d_bare:
        return True, 'skeleton'

    return False, 'none'


def calculate_step_coverage(gherkin_steps: List[Tuple[str, str]],
                            step_definitions: List[str]) -> Dict[str, Any]:
    """
    Calcula cobertura detalhada de steps.
    """
    if not gherkin_steps:
        return {
            'coverage_ratio': 1.0 if not step_definitions else 0.0,
            'precision_ratio': 1.0 if not step_definitions else 0.0,
            'match_quality': 'perfect' if not step_definitions else 'empty'
        }

    if not step_definitions:
        return {
            'coverage_ratio': 0.0,
            'precision_ratio': 0.0,
            'match_quality': 'missing_all'
        }

    matched_count = 0
    exact_matches = 0
    used_defs = set()
    match_types = []

    for step_type, gherkin_text in gherkin_steps:
        for idx, step_def in enumerate(step_definitions):
            matched, match_type = steps_match_advanced(gherkin_text, step_def)
            if matched:
                matched_count += 1
                used_defs.add(idx)
                match_types.append(match_type)
                if match_type == 'exact':
                    exact_matches += 1
                break

    coverage_ratio = matched_count / len(gherkin_steps)
    precision_ratio = len(used_defs) / len(step_definitions)
    exact_ratio = exact_matches / \
        len(gherkin_steps) if len(gherkin_steps) > 0 else 0

    # Determina qualidade do match
    if coverage_ratio >= 0.95 and precision_ratio >= 0.8 and exact_ratio >= 0.8:
        match_quality = 'perfect'
    elif coverage_ratio >= 0.95 and precision_ratio >= 0.6:
        match_quality = 'excellent'
    elif coverage_ratio >= 0.8:
        match_quality = 'good'
    elif coverage_ratio >= 0.5:
        match_quality = 'partial'
    else:
        match_quality = 'poor'

    return {
        'coverage_ratio': coverage_ratio,
        'precision_ratio': precision_ratio,
        'exact_ratio': exact_ratio,
        'match_quality': match_quality,
        'match_types': match_types
    }


def compare_steps_enhanced(gherkin_steps: List[Tuple[str, str]],
                           step_definitions: List[str],
                           background_steps: List[Tuple[str, str]]) -> Dict[str, Any]:
    """
    MELHORIA CRÍTICA: Comparação que exclui step definitions correspondentes ao Background.
    """
    matched_gherkin_steps: List[Tuple[str, str, str]] = []
    unmatched_gherkin_steps: List[Tuple[str, str]] = []
    used_defs_indices = set()
    background_defs_indices = set()

    # NOVO: Identifica step definitions que correspondem ao Background
    for bg_type, bg_text in background_steps:
        for idx, step_def in enumerate(step_definitions):
            is_match, _ = steps_match_advanced(bg_text, step_def)
            if is_match:
                background_defs_indices.add(idx)
                break

    # Match de steps dos cenários (excluindo Background)
    for step_type, gherkin_text in gherkin_steps:
        matched = False
        for idx, step_def in enumerate(step_definitions):
            is_match, match_type = steps_match_advanced(gherkin_text, step_def)
            if is_match:
                matched = True
                matched_gherkin_steps.append(
                    (step_type, gherkin_text, match_type))
                used_defs_indices.add(idx)
                break

        if not matched:
            unmatched_gherkin_steps.append((step_type, gherkin_text))

    # CRÍTICO: Excess step defs = step defs não usados E não do Background
    all_used_indices = used_defs_indices | background_defs_indices
    excess_step_defs = [
        step_definitions[i] for i in range(len(step_definitions))
        if i not in all_used_indices
    ]

    coverage_metrics = calculate_step_coverage(gherkin_steps, step_definitions)

    return {
        'matched_steps': [(t, txt) for t, txt, _ in matched_gherkin_steps],
        'matched_steps_with_type': matched_gherkin_steps,
        'unmatched_gherkin_steps': unmatched_gherkin_steps,
        'excess_step_defs': excess_step_defs,
        'background_step_defs': [step_definitions[i] for i in background_defs_indices],
        'coverage_metrics': coverage_metrics
    }


def classify_entry_improved(entry: Dict[str, Any], debug: bool = False) -> Tuple[str, Dict[str, Any]]:
    """
    Classificação melhorada com tratamento correto do Background.
    """
    feature_content = entry.get('feature_content') or ''
    matched_content = entry.get('matched_content') or ''
    language = entry.get('language') or 'java'

    # Extração
    background_steps = extract_background_steps(feature_content)
    gherkin_steps = extract_gherkin_steps(feature_content)
    step_defs = extract_step_definitions_unified(matched_content, language)

    # Proteção extra (defensiva): Filtra qualquer Gherkin step que pareça corresponder ao Background.
    # Isso garante que, mesmo que a remoção do Background falhe por formatação estranha,
    # esses passos não serão avaliados como "unmatched".
    if background_steps and gherkin_steps:
        filtered_gherkin = []
        for stype, gtext in gherkin_steps:
            is_bg_equivalent = False
            for bg_type, bg_text in background_steps:
                bg_matches_g, _ = steps_match_advanced(gtext, bg_text)
                if bg_matches_g:
                    is_bg_equivalent = True
                    break
            if not is_bg_equivalent:
                filtered_gherkin.append((stype, gtext))
        # Se houve filtragem, substitui a lista para as próximas etapas
        if len(filtered_gherkin) != len(gherkin_steps):
            if debug:
                print(f"[DEBUG] Filtrados {len(gherkin_steps)-len(filtered_gherkin)} passos que eram equivalentes ao Background.")
            gherkin_steps = filtered_gherkin

    if debug and (gherkin_steps or step_defs or background_steps):
        print(f"\n{'='*80}")
        print(f"Repository: {entry.get('repository', 'unknown')}")
        print(
            f"Language: {language} (canonical: {get_language_canonical(language)})")
        print(f"\nBackground steps ({len(background_steps)}):")
        for i, (st, txt) in enumerate(background_steps):
            print(f"  [{i}] {st}: {repr(txt)}")
        print(f"\nGherkin steps ({len(gherkin_steps)}):")
        for i, (st, txt) in enumerate(gherkin_steps):
            norm = normalize_text_for_comparison(txt)
            print(f"  [{i}] {st}: {repr(txt)}")
            print(f"       normalized: {repr(norm)}")
        print(f"\nStep definitions ({len(step_defs)}):")
        for i, sd in enumerate(step_defs):
            norm = normalize_text_for_comparison(sd)
            print(f"  [{i}] {repr(sd)}")
            print(f"       normalized: {repr(norm)}")
        print(f"{'='*80}")

    # Caso especial: ambos vazios
    if not gherkin_steps and not step_defs:
        classification = 'exact_match'
        comparison = {
            'matched_steps': [],
            'matched_steps_with_type': [],
            'unmatched_gherkin_steps': [],
            'excess_step_defs': [],
            'background_step_defs': [],
            'coverage_metrics': {
                'coverage_ratio': 1.0,
                'precision_ratio': 1.0,
                'exact_ratio': 1.0,
                'match_quality': 'perfect'
            }
        }
    else:
        # Comparação avançada COM background
        comparison = compare_steps_enhanced(gherkin_steps, step_defs, background_steps)

        has_missing = len(comparison['unmatched_gherkin_steps']) > 0
        has_excess = len(comparison['excess_step_defs']) > 0
        coverage_metrics = comparison['coverage_metrics']

        # Lógica de Classificação
        if not has_missing and not has_excess:
            classification = 'exact_match'
        elif coverage_metrics['match_quality'] in ['perfect', 'excellent'] and not has_excess:
            classification = 'exact_match'
        elif has_missing and coverage_metrics['coverage_ratio'] < 0.95:
            classification = 'missing_gherkin'
        elif has_excess and coverage_metrics['precision_ratio'] < 0.8:
            classification = 'excess_gherkin'
        elif has_missing:
            classification = 'missing_gherkin'
        else:
            classification = 'excess_gherkin'

    # Enriquece resultado
    enriched = entry.copy()
    enriched['analysis'] = {
        'total_background_steps': len(background_steps),
        'total_gherkin_steps': len(gherkin_steps),
        'total_step_definitions': len(step_defs),
        'matched_steps_count': len(comparison['matched_steps']),
        'unmatched_gherkin_steps_count': len(comparison['unmatched_gherkin_steps']),
        'excess_step_defs_count': len(comparison['excess_step_defs']),
        'background_step_defs_count': len(comparison.get('background_step_defs', [])),
        'matched_steps': comparison['matched_steps'],
        'unmatched_gherkin_steps': comparison['unmatched_gherkin_steps'],
        'excess_step_defs': comparison['excess_step_defs'],
        'background_step_defs': comparison.get('background_step_defs', []),
        'coverage_metrics': comparison['coverage_metrics'],
        'classification_quality': comparison['coverage_metrics'].get('match_quality', 'unknown')
    }

    return classification, enriched


def process_dataset(input_data: List[Dict[str, Any]], debug: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """Processa uma lista de entradas do dataset e as classifica."""
    exact_match = []
    missing_gherkin = []
    excess_gherkin = []
    quality_stats = {
        'perfect': 0, 'excellent': 0, 'good': 0, 'partial': 0, 'poor': 0, 'empty': 0, 'missing_all': 0
    }
    total = len(input_data)

    for i, entry in enumerate(input_data):
        if (i + 1) % 100 == 0:
            print(f"Processando entrada {i+1}/{total}...")

        classification, enriched_entry = classify_entry_improved(entry, debug)

        if classification == 'exact_match':
            exact_match.append(enriched_entry)
        elif classification == 'missing_gherkin':
            missing_gherkin.append(enriched_entry)
        elif classification == 'excess_gherkin':
            excess_gherkin.append(enriched_entry)

        quality = enriched_entry['analysis']['coverage_metrics'].get(
            'match_quality', 'unknown')
        if quality in quality_stats:
            quality_stats[quality] += 1

    print("\n" + "="*60)
    print("RESUMO DO PROCESSAMENTO")
    print(f"Total de entradas processadas: {total}")
    print(f'  exact_match: {len(exact_match)}')
    print(f'  missing_gherkin: {len(missing_gherkin)}')
    print(f'  excess_gherkin: {len(excess_gherkin)}')
    print(f'\nQualidade dos matches:')
    print(f'  Perfect: {quality_stats["perfect"]}')
    print(f'  Excellent: {quality_stats["excellent"]}')
    print(f'  Good: {quality_stats["good"]}')
    print(f'  Partial: {quality_stats["partial"]}')
    print(f'  Poor: {quality_stats["poor"]}')
    print(f'{"="*60}')

    return {
        'exact_match': exact_match,
        'missing_gherkin': missing_gherkin,
        'excess_gherkin': excess_gherkin,
        'statistics': quality_stats
    }


def sanitize_stem(stem: str) -> str:
    # deixa só [a-zA-Z0-9_-.] e troca espaços por _
    stem = stem.replace(' ', '_')
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', stem)

def main():
    output_dir = None
    debug = False

    # Argumentos esperados:
    #   python main.py <input_file> [output_dir] [--debug]
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
        output_dir = sys.argv[2]
    if "--debug" in sys.argv:
        debug = True

    try:
        print(f'📂 Carregando dataset de {input_file}...')
        with open(input_file, 'r', encoding='utf-8') as f:
            input_data = json.load(f)

        print(f'Entradas carregadas: {len(input_data)}')
        result = process_dataset(input_data, debug=debug)

        # === NOVO: saída personalizada ou gerada automaticamente ===
        if not output_dir:
            stem = os.path.splitext(os.path.basename(input_file))[0]
            stem = sanitize_stem(stem)
            output_dir = os.path.join('./data', f'{stem}_improved')

        os.makedirs(output_dir, exist_ok=True)

        print(f'💾 Salvando resultados em: {output_dir}')

        with open(os.path.join(output_dir, 'exact_match_dataset.json'), 'w', encoding='utf-8') as f:
            json.dump(result['exact_match'], f, indent=2, ensure_ascii=False)

        with open(os.path.join(output_dir, 'missing_gherkin_dataset.json'), 'w', encoding='utf-8') as f:
            json.dump(result['missing_gherkin'], f, indent=2, ensure_ascii=False)

        with open(os.path.join(output_dir, 'excess_gherkin_dataset.json'), 'w', encoding='utf-8') as f:
            json.dump(result['excess_gherkin'], f, indent=2, ensure_ascii=False)

        with open(os.path.join(output_dir, 'statistics.json'), 'w', encoding='utf-8') as f:
            json.dump(result['statistics'], f, indent=2, ensure_ascii=False)

        print(f'\n✅ Resultados salvos com sucesso em: {output_dir}')

    except FileNotFoundError:
        print(f'❌ Erro: arquivo não encontrado: {input_file}')
    except json.JSONDecodeError:
        print(f'❌ Erro: JSON inválido em {input_file}')
    except Exception as e:
        print(f'❌ Erro inesperado: {e}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()