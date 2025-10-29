import re
import os
from typing import List, Dict, Tuple, Optional, Set
from datetime import datetime
import logging

class GherkinStepCleaner:
    """
    Remove métodos de step definitions excessivos de arquivos de teste Gherkin.
    Suporta: Java, Kotlin, Scala, Ruby, JavaScript, TypeScript, Node.js
    Com análise de dependências internas entre steps.
    """

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir or "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        self.setup_logging()
        self._setup_patterns()
        self.logger.info("GherkinStepCleaner inicializado")

    def _setup_patterns(self):
        """Configura padrões de regex para cada linguagem"""
        self.patterns = {
            'java': {'language_family': 'jvm'},
            'kotlin': {'language_family': 'jvm'},
            'scala': {'language_family': 'jvm'},
            'ruby': {'language_family': 'ruby'},
            'javascript': {'language_family': 'js'},
            'typescript': {'language_family': 'js'},
            'nodejs': {'language_family': 'js'}
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

    def normalize_pattern_for_matching(self, pattern: str) -> str:
        """
        Normaliza um pattern de regex para matching flexível.
        Remove âncoras (^, $), espaços extras, mas mantém a estrutura do regex.
        """
        if not pattern:
            return ""
        
        normalized = pattern.strip()
        if normalized.startswith('^'):
            normalized = normalized[1:]
        if normalized.endswith('$'):
            normalized = normalized[:-1]
        
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        normalized = normalized.strip('/')
        
        return normalized

    def extract_step_pattern_ruby(self, line: str) -> Optional[str]:
        """Extrai o pattern exato de um step definition Ruby."""
        # Tenta capturar /regex/
        match = re.search(r'^\s*(?:Given|When|Then|And|But)\s*\(\s*/(.+?)/', line)
        if match:
            return match.group(1)
        
        # Tenta capturar "string" ou 'string'
        match = re.search(r'^\s*(?:Given|When|Then|And|But)\s*\(\s*["\'](.+?)["\']', line)
        if match:
            return match.group(1)
        
        return None

    def extract_step_pattern_js(self, line: str) -> Optional[str]:
        """Extrai o pattern exato de um step definition JS/TS."""
        match = re.search(r'(?:Given|When|Then|And|But|defineStep)\s*\(\s*(["\'\`])(.+?)\1', line)
        if match:
            return match.group(2)
        return None

    def extract_step_pattern_jvm(self, line: str) -> Optional[str]:
        """Extrai o pattern exato de um step definition JVM."""
        match = re.search(r'@(?:Given|When|Then|And|But)\s*\(\s*["\'](.+?)["\']', line)
        if match:
            return match.group(1)
        return None

    def extract_step_pattern(self, line: str, language: str) -> Optional[str]:
        """Extrai o pattern de step definition baseado na linguagem."""
        family = self.patterns[language]['language_family']
        
        if family == 'ruby':
            return self.extract_step_pattern_ruby(line)
        elif family == 'js':
            return self.extract_step_pattern_js(line)
        elif family == 'jvm':
            return self.extract_step_pattern_jvm(line)
        
        return None

    def find_internal_step_references_ruby(self, method_body: str) -> List[str]:
        """
        Encontra referências a outros steps dentro de um método Ruby.
        Detecta patterns como: steps %( Given "..." Then "..." )
        """
        references = []
        
        self.logger.debug(f"  Analisando corpo do método para referências internas...")
        
        # Procurar por blocos steps %( ... ) ou steps %{ ... }
        patterns = [
            r'steps\s+%\(\s*(.+?)\s*\)',  # steps %( ... )
            r'steps\s+%\{\s*(.+?)\s*\}',  # steps %{ ... }
            r'steps\s+%\[\s*(.+?)\s*\]',  # steps %[ ... ]
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, method_body, re.DOTALL):
                steps_block = match.group(1)
                self.logger.debug(f"  Bloco steps encontrado: {steps_block[:100]}...")
                
                # Extrair cada step individual dentro do bloco
                # O texto dentro pode ter escapes como \"
                # Precisamos capturar: Given the date is \"2014 Feb 5th 7:05am\"
                
                # Primeiro, vamos tentar encontrar padrões mais específicos
                # Formato 1: Given "texto com \" escapes"
                # Formato 2: Given 'texto'
                # Formato 3: Given /regex/
                
                # Usar regex mais robusto que captura texto entre aspas com escapes
                step_patterns = [
                    # Captura: Given "texto com \" dentro"
                    r'(?:Given|When|Then|And|But)\s+"([^"\\]*(?:\\.[^"\\]*)*)"',
                    # Captura: Given 'texto'
                    r"(?:Given|When|Then|And|But)\s+'([^'\\]*(?:\\.[^'\\]*)*)'",
                    # Captura sem aspas mas preservando estrutura
                    r'(?:Given|When|Then|And|But)\s+(.+?)(?=\s+(?:Given|When|Then|And|But)|$)',
                ]
                
                for step_pattern in step_patterns:
                    for step_match in re.finditer(step_pattern, steps_block, re.DOTALL):
                        step_text = step_match.group(1).strip()
                        
                        # Remover quebras de linha e espaços extras
                        step_text = re.sub(r'\s+', ' ', step_text).strip()
                        
                        if step_text:
                            # Unescape: converter \" para "
                            step_text_unescaped = step_text.replace('\\"', '"').replace("\\'", "'")
                            
                            references.append(step_text_unescaped)
                            self.logger.debug(f"    ✓ Referência encontrada: '{step_text_unescaped}'")
        
        self.logger.debug(f"  Total de {len(references)} referências encontradas")
        return references

    def find_internal_step_references_js(self, method_body: str) -> List[str]:
        """
        Encontra referências a outros steps dentro de um método JS/TS.
        """
        references = []
        
        patterns = [
            r'this\.\s*(?:Given|When|Then|And|But)\s*\(\s*["\'\`](.+?)["\'\`]',
            r'await\s+this\.\s*(?:Given|When|Then|And|But)\s*\(\s*["\'\`](.+?)["\'\`]',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, method_body, re.DOTALL):
                step_text = match.group(1)
                references.append(step_text)
                self.logger.debug(f"    -> Referência interna: '{step_text}'")
        
        return references

    def find_internal_step_references_jvm(self, method_body: str) -> List[str]:
        """
        Encontra referências a outros steps dentro de um método JVM.
        """
        references = []
        
        patterns = [
            r'(?:executeStep|runStep|callStep)\s*\(\s*["\'](.+?)["\']',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, method_body, re.DOTALL):
                step_text = match.group(1)
                references.append(step_text)
                self.logger.debug(f"    -> Referência interna: '{step_text}'")
        
        return references

    def find_internal_step_references(self, method_body: str, language: str) -> List[str]:
        """
        Encontra referências a outros steps dentro de um método.
        """
        family = self.patterns[language]['language_family']
        
        if family == 'ruby':
            return self.find_internal_step_references_ruby(method_body)
        elif family == 'js':
            return self.find_internal_step_references_js(method_body)
        elif family == 'jvm':
            return self.find_internal_step_references_jvm(method_body)
        
        return []

    def find_method_boundaries_ruby(self, lines: List[str], step_line: int) -> Tuple[int, int]:
        """Encontra os limites completos de um método Ruby."""
        n = len(lines)
        method_start = step_line
        
        for i in range(step_line, min(n, step_line + 3)):
            line = lines[i]
            
            if re.search(r'\bdo\b', line):
                depth = 1
                for j in range(i + 1, n):
                    current_line = lines[j]
                    depth += len(re.findall(r'\bdo\b', current_line))
                    depth -= len(re.findall(r'\bend\b', current_line))
                    if depth <= 0:
                        return method_start, j
                return -1, -1
            
            elif '{' in line:
                brace_count = line.count('{') - line.count('}')
                if brace_count == 0:
                    return method_start, i
                for j in range(i + 1, n):
                    brace_count += lines[j].count('{') - lines[j].count('}')
                    if brace_count <= 0:
                        return method_start, j
                return -1, -1
        
        return -1, -1

    def find_method_boundaries_js(self, lines: List[str], step_line: int) -> Tuple[int, int]:
        """Encontra os limites completos de uma função JS/TS."""
        n = len(lines)
        method_start = step_line
        brace_count = 0
        
        for i in range(step_line, min(n, step_line + 10)):
            line = lines[i]
            if '{' in line:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0:
                    return method_start, i
                for j in range(i + 1, n):
                    current = lines[j]
                    brace_count += current.count('{') - current.count('}')
                    if brace_count <= 0:
                        return method_start, j
                return -1, -1
        return -1, -1

    def find_method_boundaries_jvm(self, lines: List[str], step_line: int) -> Tuple[int, int]:
        """Encontra os limites completos de um método JVM."""
        n = len(lines)
        method_start = step_line
        brace_count = 0
        
        for i in range(step_line, min(n, step_line + 15)):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith('@'):
                continue
            if '{' in line:
                cleaned = re.sub(r'"[^"]*"', '', line)
                cleaned = re.sub(r"'[^']*'", '', cleaned)
                brace_count = cleaned.count('{') - cleaned.count('}')
                if brace_count == 0:
                    return method_start, i
                for j in range(i + 1, n):
                    current = lines[j]
                    cleaned = re.sub(r'"[^"]*"', '', current)
                    cleaned = re.sub(r"'[^']*'", '', cleaned)
                    brace_count += cleaned.count('{') - cleaned.count('}')
                    if brace_count <= 0:
                        return method_start, j
                return -1, -1
        return -1, -1

    def find_method_boundaries(self, lines: List[str], step_line: int, language: str) -> Tuple[int, int]:
        """Dispatcher para encontrar limites de método."""
        if language not in self.patterns:
            return -1, -1
        family = self.patterns[language]['language_family']
        if family == 'ruby':
            return self.find_method_boundaries_ruby(lines, step_line)
        elif family == 'js':
            return self.find_method_boundaries_js(lines, step_line)
        elif family == 'jvm':
            return self.find_method_boundaries_jvm(lines, step_line)
        return -1, -1

    def extract_step_definitions(self, code: str, language: str) -> List[Dict]:
        """
        Extrai todos os step definitions do código fonte.
        """
        if not code:
            return []
        
        language = language.lower()
        if language not in self.patterns:
            self.logger.error(f"Linguagem não suportada: {language}")
            return []
        
        lines = code.replace('\r\n', '\n').replace('\r', '\n').splitlines()
        extracted = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue
            
            if not re.search(r'\b(Given|When|Then|And|But|defineStep)\b', line):
                continue
            
            pattern = self.extract_step_pattern(line, language)
            if not pattern:
                continue
            
            step_type_match = re.search(r'\b(Given|When|Then|And|But|defineStep)\b', line)
            step_type = step_type_match.group(1) if step_type_match else 'Unknown'
            
            start_line, end_line = self.find_method_boundaries(lines, i, language)
            if start_line == -1 or end_line == -1:
                self.logger.warning(f"Não foi possível encontrar limites para linha {i}: {pattern}")
                continue
            
            # Extrair corpo do método
            method_body = '\n'.join(lines[start_line:end_line + 1])
            
            # Detectar referências internas
            self.logger.debug(f"\n{'='*60}")
            self.logger.debug(f"Analisando step: {step_type} '{pattern}'")
            internal_references = self.find_internal_step_references(method_body, language)
            
            extracted.append({
                'step_type': step_type,
                'step_pattern': pattern,
                'step_pattern_normalized': self.normalize_pattern_for_matching(pattern),
                'annotation_line': i,
                'start_line': start_line,
                'end_line': end_line,
                'internal_references': internal_references,
                'internal_references_normalized': [
                    self.normalize_pattern_for_matching(ref) 
                    for ref in internal_references
                ]
            })
            
            if internal_references:
                self.logger.info(f"✓ Extraído: {step_type} '{pattern}' com {len(internal_references)} referências")
            else:
                self.logger.debug(f"✓ Extraído: {step_type} '{pattern}'")
        
        self.logger.info(f"\nTotal de {len(extracted)} step definitions extraídos")
        return extracted

    def remove_excess_steps(self, code: str, language: str, excess_steps: List) -> Tuple[str, List[str], List]:
        """
        Remove step definitions excedentes do código.
        PROTEGE steps que são referenciados internamente por QUALQUER outro step.
        PROTEGE steps que contêm substeps NÃO marcados para remoção.
        """
        if not code or not excess_steps:
            return code, [], excess_steps
        
        language = language.lower()
        if language not in self.patterns:
            raise ValueError(f"Linguagem não suportada: {language}")
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"INICIANDO REMOÇÃO DE STEP DEFINITIONS EXCEDENTES")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Linguagem: {language}")
        self.logger.info(f"Steps excedentes: {len(excess_steps)}")
        
        # Extrair todos os step definitions
        all_step_defs = self.extract_step_definitions(code, language)
        
        if not all_step_defs:
            self.logger.warning("Nenhum step definition encontrado no código")
            return code, [], excess_steps
        
        # Criar conjunto de patterns excedentes normalizados
        excess_patterns_normalized = {}
        for excess in excess_steps:
            if isinstance(excess, (list, tuple)) and len(excess) >= 2:
                pattern = excess[1]
            elif isinstance(excess, str):
                pattern = excess
            else:
                continue
            
            pattern_normalized = self.normalize_pattern_for_matching(pattern)
            excess_patterns_normalized[pattern_normalized] = excess
            self.logger.debug(f"Excess: '{pattern}' -> Normalizado: '{pattern_normalized}'")
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"ANÁLISE DE DEPENDÊNCIAS")
        self.logger.info(f"{'='*80}")
        
        # Construir conjunto de patterns protegidos
        protected_patterns: Set[str] = set()
        protection_reasons = {}
        
        # REGRA 1: Proteger steps que são referenciados por outros steps
        for step_def in all_step_defs:
            pattern_normalized = step_def['step_pattern_normalized']
            internal_refs = step_def['internal_references_normalized']
            
            if internal_refs:
                self.logger.info(f"\n📦 Step '{pattern_normalized}' referencia {len(internal_refs)} outros steps:")
                
                for ref in internal_refs:
                    protected_patterns.add(ref)
                    protection_reasons[ref] = f"Referenciado por: '{pattern_normalized}'"
                    self.logger.info(f"  🔒 Protegendo: '{ref}'")
        
        # REGRA 2: Proteger steps que referenciam substeps NÃO marcados para remoção
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"ANÁLISE DE SUBSTEPS NÃO MARCADOS PARA REMOÇÃO")
        self.logger.info(f"{'='*80}")
        
        for step_def in all_step_defs:
            pattern_normalized = step_def['step_pattern_normalized']
            pattern_original = step_def['step_pattern']
            internal_refs = step_def['internal_references_normalized']
            
            # Se este step está marcado para remoção E tem substeps
            if pattern_normalized in excess_patterns_normalized and internal_refs:
                self.logger.info(f"\n🔍 Analisando substeps de '{pattern_original}':")
                
                has_non_excess_substep = False
                non_excess_substeps = []
                
                for ref in internal_refs:
                    # Verificar se este substep NÃO está na lista de excess
                    if ref not in excess_patterns_normalized:
                        has_non_excess_substep = True
                        non_excess_substeps.append(ref)
                        self.logger.info(f"  ✓ Substep NÃO marcado para remoção: '{ref}'")
                    else:
                        self.logger.info(f"  ✗ Substep marcado para remoção: '{ref}'")
                
                # Se tem pelo menos um substep não marcado para remoção, proteger o step principal
                if has_non_excess_substep:
                    protected_patterns.add(pattern_normalized)
                    protection_reasons[pattern_normalized] = f"Contém {len(non_excess_substeps)} substep(s) não marcado(s) para remoção"
                    self.logger.info(f"  🛡️  PROTEGENDO step principal '{pattern_original}'")
                    self.logger.info(f"     Razão: Contém substeps que devem ser mantidos")
        
        if protected_patterns:
            self.logger.info(f"\n✅ Total de {len(protected_patterns)} patterns protegidos")
            self.logger.info(f"\nResumo das proteções:")
            for pattern in protected_patterns:
                reason = protection_reasons.get(pattern, 'Motivo desconhecido')
                self.logger.info(f"  🛡️  '{pattern}' - {reason}")
        else:
            self.logger.info(f"\n⚠️ Nenhum pattern protegido encontrado")
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"DECISÕES DE REMOÇÃO")
        self.logger.info(f"{'='*80}")
        
        # Identificar steps a serem removidos
        lines_to_remove = set()
        removed_methods = []
        matched_patterns = set()
        protected_count = 0
        
        for step_def in all_step_defs:
            pattern_original = step_def['step_pattern']
            pattern_normalized = step_def['step_pattern_normalized']
            
            if pattern_normalized in excess_patterns_normalized:
                if pattern_normalized in protected_patterns:
                    protected_by = protection_reasons.get(pattern_normalized, 'unknown')
                    self.logger.info(f"\n✓ MANTER (protegido): '{pattern_original}'")
                    self.logger.info(f"  Razão: {protected_by}")
                    protected_count += 1
                else:
                    for line_num in range(step_def['start_line'], step_def['end_line'] + 1):
                        lines_to_remove.add(line_num)
                    
                    removed_methods.append(f"{step_def['step_type']}: \"{pattern_original}\"")
                    matched_patterns.add(pattern_normalized)
                    
                    self.logger.info(f"\n✗ REMOVER: '{pattern_original}'")
                    self.logger.info(f"  Linhas: {step_def['start_line']}-{step_def['end_line']}")
        
        # Verificar patterns não encontrados
        not_found = set(excess_patterns_normalized.keys()) - matched_patterns - protected_patterns
        if not_found:
            self.logger.warning(f"\n⚠️ {len(not_found)} patterns NÃO ENCONTRADOS:")
            for nf in not_found:
                self.logger.warning(f"  - '{nf}'")
        
        if not lines_to_remove:
            self.logger.info("\n⚠️ Nenhuma linha marcada para remoção")
            return code, [], excess_steps
        
        # Criar código limpo
        lines = code.replace('\r\n', '\n').replace('\r', '\n').splitlines()
        cleaned_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]
        
        cleaned_code = '\n'.join(cleaned_lines)
        cleaned_code = re.sub(r'\n{3,}', '\n\n', cleaned_code)
        
        if code.endswith('\n') and not cleaned_code.endswith('\n'):
            cleaned_code += '\n'
        
        remaining_excess = [
            excess_patterns_normalized[pn] 
            for pn in excess_patterns_normalized 
            if pn not in matched_patterns
        ]
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"RESULTADO FINAL")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Linhas originais: {len(lines)}")
        self.logger.info(f"Linhas removidas: {len(lines) - len(cleaned_lines)}")
        self.logger.info(f"Linhas finais: {len(cleaned_lines)}")
        self.logger.info(f"Métodos removidos: {len(removed_methods)}")
        self.logger.info(f"Steps protegidos: {protected_count}")
        self.logger.info(f"Steps restantes na lista: {len(remaining_excess)}")
        self.logger.info(f"{'='*80}\n")
        
        return cleaned_code, removed_methods, remaining_excess