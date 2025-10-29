#!/usr/bin/env python3
"""
Pipeline completo para processamento de datasets Gherkin
Executa: comparação -> validação -> limpeza -> unificação
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import logging
import shutil

# Imports dos módulos existentes
from core.validate_type_of_pairs import process_dataset as validate_dataset
from core.gherkin_step_cleaner import GherkinStepCleaner


class GherkinPipeline:
    """Pipeline completo para processamento de datasets Gherkin"""
    
    def __init__(self, exploration_file: str, exploitation_file: str, output_dir: str = "./pipeline_output"):
        self.exploration_file = Path(exploration_file)
        self.exploitation_file = Path(exploitation_file)
        self.output_dir = Path(output_dir)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Estrutura de diretórios
        self.dirs = {
            'root': self.output_dir,
            'comparison': self.output_dir / '01_comparison',
            'validation': self.output_dir / '02_validation',
            'cleaning': self.output_dir / '03_cleaning',
            'final': self.output_dir / '04_final',
            'logs': self.output_dir / 'logs'
        }
        
        # Configurar logging
        self._setup_logging()
        
        # Estatísticas
        self.stats = {
            'start_time': datetime.now(),
            'exploration_entries': 0,
            'exploitation_entries': 0,
            'comparison_results': {},
            'validation_results': {},
            'cleaning_results': {},
            'final_dataset_size': 0,
            'final_no_analysis_file': None
        }
    
    def _clear_output_dir(self):
        """
        Remove recursivamente o diretório de output se existir.
        Usado para garantir execução limpa a cada run.
        """
        out = self.output_dir
        if out.exists():
            # log antes de apagar (evita perder dados sem registro)
            self.logger.info(f"Removendo diretório de saída existente: {out}")
            try:
                shutil.rmtree(out)
            except Exception as e:
                self.logger.error(f"Erro ao remover diretório de saída {out}: {e}")
        else:
            self.logger.debug(f"Diretório de saída não existe, nada a apagar: {out}")
    
    def _setup_logging(self):
        """Configura sistema de logging"""
        os.makedirs(self.dirs['logs'], exist_ok=True)
        
        log_file = self.dirs['logs'] / f'pipeline_{self.timestamp}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger('GherkinPipeline')
        self.logger.info("="*80)
        self.logger.info("GHERKIN DATASET PIPELINE INICIADO")
        self.logger.info("="*80)
        self.logger.info(f"Exploration: {self.exploration_file}")
        self.logger.info(f"Exploitation: {self.exploitation_file}")
        self.logger.info(f"Output: {self.output_dir}")
    
    def _create_directories(self):
        """Cria estrutura de diretórios"""
        for dir_name, dir_path in self.dirs.items():
            os.makedirs(dir_path, exist_ok=True)
            self.logger.info(f"Diretório criado: {dir_path}")
    
    def _load_json(self, filepath: Path) -> List[Dict]:
        """Carrega arquivo JSON"""
        self.logger.info(f"Carregando {filepath.name}...")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.logger.info(f"✓ {len(data)} entradas carregadas")
        return data
    
    def _save_json(self, data: List[Dict], filepath: Path):
        """Salva arquivo JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.logger.info(f"✓ Salvo: {filepath.name} ({len(data)} entradas)")
    
    def step1_compare_datasets(self) -> Dict[str, Path]:
        """
        Passo 1: Compara exploration e exploitation
        Gera: common, exploration_only, exploitation_only
        """
        self.logger.info("\n" + "="*80)
        self.logger.info("PASSO 1: COMPARAÇÃO DE DATASETS")
        self.logger.info("="*80)
        
        exploration = self._load_json(self.exploration_file)
        exploitation = self._load_json(self.exploitation_file)
        
        self.stats['exploration_entries'] = len(exploration)
        self.stats['exploitation_entries'] = len(exploitation)
        
        # Função de chave composta (do common_files.py)
        def entry_key(entry):
            return (
                entry.get("repository"),
                entry.get("language"),
                entry.get("feature_file"),
                tuple(sorted([u.get("file") for u in entry.get("used_in", [])]))
            )
        
        # Criar dicionários (com detecção de possíveis colisões de chave)
        exploration_dict = {}
        exploration_key_counts = {}
        for e in exploration:
            k = entry_key(e)
            if k in exploration_dict:
                exploration_key_counts[k] = exploration_key_counts.get(k, 1) + 1
                self.logger.warning(f"Duplicate key in exploration dataset for key {k!r}. Count={exploration_key_counts[k]}")
            exploration_dict[k] = e
        
        exploitation_dict = {}
        exploitation_key_counts = {}
        for e in exploitation:
            k = entry_key(e)
            if k in exploitation_dict:
                exploitation_key_counts[k] = exploitation_key_counts.get(k, 1) + 1
                self.logger.warning(f"Duplicate key in exploitation dataset for key {k!r}. Count={exploitation_key_counts[k]}")
            exploitation_dict[k] = e
        
        # Conjuntos de chaves
        exploration_keys = set(exploration_dict.keys())
        exploitation_keys = set(exploitation_dict.keys())
        
        common_keys = exploration_keys & exploitation_keys
        exploration_only_keys = exploration_keys - exploitation_keys
        # FIX: antes estava exploitation_keys - exploitation_keys (sempre vazio)
        exploitation_only_keys = exploitation_keys - exploration_keys
        
        # Gerar datasets
        common = [exploration_dict[k] for k in sorted(common_keys)]
        exploration_only = [exploration_dict[k] for k in sorted(exploration_only_keys)]
        exploitation_only = [exploitation_dict[k] for k in sorted(exploitation_only_keys)]
        
        # Salvar
        output_files = {
            'common': self.dirs['comparison'] / 'common_exploration_exploitation.json',
            'exploration_only': self.dirs['comparison'] / 'exploration_only.json',
            'exploitation_only': self.dirs['comparison'] / 'exploitation_only.json'
        }
        
        self._save_json(common, output_files['common'])
        self._save_json(exploration_only, output_files['exploration_only'])
        self._save_json(exploitation_only, output_files['exploitation_only'])
        
        # Estatísticas
        self.stats['comparison_results'] = {
            'common': len(common),
            'exploration_only': len(exploration_only),
            'exploitation_only': len(exploitation_only)
        }
        
        self.logger.info(f"\n📊 Resultados da comparação:")
        self.logger.info(f"   Comuns: {len(common)}")
        self.logger.info(f"   Apenas Exploration: {len(exploration_only)}")
        self.logger.info(f"   Apenas Exploitation: {len(exploitation_only)}")
        
        return output_files
    
    def step2_validate_pairs(self, comparison_files: Dict[str, Path]) -> Dict[str, Dict[str, Path]]:
        """
        Passo 2: Valida tipos de pares para cada dataset
        Gera: exact_match, missing_gherkin, excess_gherkin
        """
        self.logger.info("\n" + "="*80)
        self.logger.info("PASSO 2: VALIDAÇÃO DE PARES")
        self.logger.info("="*80)
        
        validation_results = {}
        
        for dataset_name, input_file in comparison_files.items():
            self.logger.info(f"\n▶ Validando: {dataset_name}")
            
            # Criar subdiretório
            dataset_dir = self.dirs['validation'] / dataset_name
            os.makedirs(dataset_dir, exist_ok=True)
            
            # Carregar e processar
            input_data = self._load_json(input_file)
            result = validate_dataset(input_data, debug=False)
            
            # Salvar resultados
            output_files = {
                'exact_match': dataset_dir / 'exact_match_dataset.json',
                'missing_gherkin': dataset_dir / 'missing_gherkin_dataset.json',
                'excess_gherkin': dataset_dir / 'excess_gherkin_dataset.json'
            }
            
            self._save_json(result['exact_match'], output_files['exact_match'])
            self._save_json(result['missing_gherkin'], output_files['missing_gherkin'])
            self._save_json(result['excess_gherkin'], output_files['excess_gherkin'])
            
            # Estatísticas
            validation_results[dataset_name] = {
                'files': output_files,
                'stats': {
                    'exact_match': len(result['exact_match']),
                    'missing_gherkin': len(result['missing_gherkin']),
                    'excess_gherkin': len(result['excess_gherkin']),
                    'quality': result['statistics']
                }
            }
            
            self.logger.info(f"   ✓ Exact match: {len(result['exact_match'])}")
            self.logger.info(f"   ✓ Missing gherkin: {len(result['missing_gherkin'])}")
            self.logger.info(f"   ✓ Excess gherkin: {len(result['excess_gherkin'])}")
        
        self.stats['validation_results'] = validation_results
        return validation_results
    
    def step3_clean_excess_gherkin(self, validation_results: Dict[str, Dict]) -> Dict[str, Path]:
        """
        Passo 3: Limpa excess_gherkin para exact_match
        Suporta: Java, Kotlin, Scala, Ruby, JavaScript, TypeScript, Node.js

        Agora também:
        - Revalida as entradas limpas e anexa os 'cleaned exact' ao exact_match original,
          garantindo que entradas que se tornaram exact após limpeza de fato entrem no merge final.
        - Salva arquivos de validação para as entradas limpas em cleaning/<dataset>/
        """
        self.logger.info("\n" + "="*80)
        self.logger.info("PASSO 3: LIMPEZA DE EXCESS GHERKIN (COM RE-VALIDAÇÃO)")
        self.logger.info("="*80)
        
        cleaned_files = {}
        
        for dataset_name, results in validation_results.items():
            excess_file = results['files']['excess_gherkin']
            
            if not excess_file.exists():
                self.logger.warning(f"⚠ Arquivo não encontrado: {excess_file}")
                continue
            
            self.logger.info(f"\n▶ Limpando: {dataset_name}")
            
            # Diretório de saída
            cleaning_dir = self.dirs['cleaning'] / dataset_name
            os.makedirs(cleaning_dir, exist_ok=True)
            
            output_file = cleaning_dir / 'excess_gherkin_cleaned.json'
            log_dir = cleaning_dir / 'logs'
            
            # Executar limpeza
            try:
                cleaner = GherkinStepCleaner(log_dir=str(log_dir))
                
                # Carregar dataset
                excess_data = self._load_json(excess_file)
                
                # Filtrar por linguagens suportadas
                supported_langs = cleaner.get_supported_languages()
                supported_entries = [
                    e for e in excess_data 
                    if e.get('language', '').lower() in supported_langs
                ]
                unsupported_entries = [
                    e for e in excess_data 
                    if e.get('language', '').lower() not in supported_langs
                ]
                
                self.logger.info(f"   Entradas suportadas: {len(supported_entries)}")
                self.logger.info(f"   Entradas não suportadas: {len(unsupported_entries)}")
                
                if unsupported_entries:
                    unsupported_langs = set(e.get('language', 'unknown').lower() for e in unsupported_entries)
                    self.logger.info(f"   Linguagens não suportadas: {', '.join(unsupported_langs)}")
                
                # Processar entradas suportadas
                cleaned_entries = []
                cleaning_stats = {
                    'total': len(supported_entries),
                    'success': 0,
                    'failed': 0,
                    'steps_removed': 0,
                    'by_language': {}
                }
                
                for i, entry in enumerate(supported_entries, 1):
                    language = entry['language'].lower()
                    code = entry['matched_content']
                    excess_steps = entry['analysis']['excess_step_defs']
                    
                    # Inicializar estatísticas por linguagem
                    if language not in cleaning_stats['by_language']:
                        cleaning_stats['by_language'][language] = {
                            'total': 0,
                            'success': 0,
                            'steps_removed': 0
                        }
                    
                    cleaning_stats['by_language'][language]['total'] += 1
                    
                    try:
                        cleaned_code, removed_methods, remaining = cleaner.remove_excess_steps(
                            code, language, excess_steps
                        )
                        
                        # Criar entrada limpa
                        cleaned_entry = entry.copy()
                        cleaned_entry['matched_content'] = cleaned_code
                        cleaned_entry['analysis']['excess_step_defs'] = remaining
                        cleaned_entry['analysis']['excess_step_defs_count'] = len(remaining)
                        cleaned_entry['cleaning_metadata'] = {
                            'cleaned_at': datetime.utcnow().isoformat(),
                            'removed_count': len(removed_methods),
                            'remaining_count': len(remaining),
                            'removed_methods': removed_methods
                        }
                        
                        cleaned_entries.append(cleaned_entry)
                        cleaning_stats['success'] += 1
                        cleaning_stats['steps_removed'] += len(removed_methods)
                        cleaning_stats['by_language'][language]['success'] += 1
                        cleaning_stats['by_language'][language]['steps_removed'] += len(removed_methods)
                        
                    except Exception as e:
                        self.logger.error(f"   ✗ Erro na entrada {i}: {e}")
                        cleaned_entries.append(entry)  # Mantém original se falhar
                        cleaning_stats['failed'] += 1
                
                # Adicionar entradas não suportadas sem modificação
                cleaned_entries.extend(unsupported_entries)
                
                # Salvar excess limpo (todas as entradas processadas, inclusive não suportadas)
                self._save_json(cleaned_entries, output_file)
                cleaned_files[dataset_name] = output_file
                
                self.logger.info(f"\n   📊 Estatísticas de limpeza:")
                self.logger.info(f"      Processadas: {cleaning_stats['total']}")
                self.logger.info(f"      Sucesso: {cleaning_stats['success']}")
                self.logger.info(f"      Falhas: {cleaning_stats['failed']}")
                self.logger.info(f"      Steps removidos: {cleaning_stats['steps_removed']}")
                
                if cleaning_stats['by_language']:
                    self.logger.info(f"\n   📊 Por linguagem:")
                    for lang, stats in cleaning_stats['by_language'].items():
                        self.logger.info(f"      {lang.upper()}: {stats['success']}/{stats['total']} entradas, "
                                       f"{stats['steps_removed']} steps removidos")
                
                # -------- RE-VALIDAÇÃO das entradas limpas --------
                self.logger.info("\n   ▶ Re-validando entradas limpas para detectar migração excess->exact...")
                revalidation = validate_dataset(cleaned_entries, debug=False)
                
                # Salvar resultados da validação da versão limpa para referência
                cleaned_validation_files = {
                    'exact_match': cleaning_dir / 'cleaned_exact_match_dataset.json',
                    'missing_gherkin': cleaning_dir / 'cleaned_missing_gherkin_dataset.json',
                    'excess_gherkin': cleaning_dir / 'cleaned_excess_gherkin_dataset.json'
                }
                self._save_json(revalidation['exact_match'], cleaned_validation_files['exact_match'])
                self._save_json(revalidation['missing_gherkin'], cleaned_validation_files['missing_gherkin'])
                self._save_json(revalidation['excess_gherkin'], cleaned_validation_files['excess_gherkin'])
                
                # Anexar cleaned exact ao exact_match original (para que entrem como exact no merge final)
                original_exact_file = results['files']['exact_match']
                original_exact = []
                if original_exact_file.exists():
                    original_exact = self._load_json(original_exact_file)
                appended_count_before = len(original_exact)
                original_exact.extend(revalidation['exact_match'])
                # remover duplicatas por chave composta opcional? (mantive append simples)
                self._save_json(original_exact, original_exact_file)
                
                appended_count_after = len(original_exact)
                migrated = len(revalidation['exact_match'])
                self.logger.info(f"   ✓ Entradas que migraram de excess -> exact: {migrated}")
                
                # Substituir arquivo excess_gherkin da validação por aquele limpo (apenas remanescentes)
                # Se não houver excess remanescente, cria um arquivo vazio
                new_excess_file = cleaned_validation_files['excess_gherkin']
                if not new_excess_file.exists():
                    # criar arquivo vazio
                    self._save_json([], new_excess_file)
                # Atualiza referencias em validation_results para usar os arquivos limpos
                results['files']['exact_match'] = original_exact_file
                results['files']['excess_gherkin'] = new_excess_file
                # Também podemos manter as cleaned_validation_files como metadados para auditoria
                results['files']['cleaned_validation'] = cleaned_validation_files
                
                # Atualizar estatísticas agregadas
                stats = results.get('stats', {})
                stats['exact_match'] = len(original_exact)
                stats['missing_gherkin'] = stats.get('missing_gherkin', 0) + len(revalidation['missing_gherkin'])
                stats['excess_gherkin'] = len(self._load_json(new_excess_file))
                # merge quality stats (simples soma)
                combined_quality = stats.get('quality', {})
                requal = revalidation.get('statistics', {})
                # soma contagens de qualidade (se disponível)
                for k, v in requal.items():
                    combined_quality[k] = combined_quality.get(k, 0) + v
                stats['quality'] = combined_quality
                results['stats'] = stats
                
                self.logger.info(f"   Atualizado exact_match total: {stats['exact_match']}")
                self.logger.info(f"   Atualizado excess_gherkin total: {stats['excess_gherkin']}")
                
            except Exception as e:
                self.logger.error(f"   ✗ Erro ao limpar {dataset_name}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
        
        return cleaned_files
    
    def step4_merge_final_dataset(self, 
                                   validation_results: Dict[str, Dict],
                                   cleaned_files: Dict[str, Path]) -> Path:
        """
        Passo 4: Unifica todos os subdatasets em um dataset final
        """
        self.logger.info("\n" + "="*80)
        self.logger.info("PASSO 4: UNIFICAÇÃO DO DATASET FINAL")
        self.logger.info("="*80)
        
        final_dataset = []
        merge_stats = {}
        
        for dataset_name, results in validation_results.items():
            self.logger.info(f"\n▶ Processando: {dataset_name}")
            
            # 1. Exact match
            exact_file = results['files']['exact_match']
            exact_data = self._load_json(exact_file)
            final_dataset.extend(exact_data)
            
            # 3. Excess gherkin limpo (se disponível) ou original
            if dataset_name in cleaned_files:
                excess_file = results['files'].get('excess_gherkin', cleaned_files[dataset_name])
                source = 'cleaned'
            else:
                excess_file = results['files']['excess_gherkin']
                source = 'original'
            
            excess_data = self._load_json(excess_file)
            final_dataset.extend(excess_data)
            
            # Estatísticas
            merge_stats[dataset_name] = {
                'exact_match': len(exact_data),
                'excess_gherkin': len(excess_data),
                'excess_source': source,
                'total': len(exact_data) + len(excess_data)
            }
            
            self.logger.info(f"   Exact match: {len(exact_data)}")
            self.logger.info(f"   Excess gherkin ({source}): {len(excess_data)}")
        
        # Salvar dataset final
        final_file = self.dirs['final'] / f'final_dataset_{self.timestamp}.json'
        self._save_json(final_dataset, final_file)
        
        self.stats['final_dataset_size'] = len(final_dataset)
        
        self.logger.info(f"\n✅ DATASET FINAL CRIADO")
        self.logger.info(f"   Total de entradas: {len(final_dataset)}")
        self.logger.info(f"   Arquivo: {final_file}")
        
        # Salvar estatísticas de merge
        merge_stats_file = self.dirs['final'] / f'merge_statistics_{self.timestamp}.json'
        with open(merge_stats_file, 'w', encoding='utf-8') as f:
            json.dump(merge_stats, f, indent=2, ensure_ascii=False)
        
        return final_file

    def generate_no_analysis_dataset(self, final_file: Path) -> Path:
        """
        Gera uma cópia do dataset final sem os objetos 'analysis' e 'cleaning_metadata'
        em cada entrada. Salva como consolidated_dataset{timestamp}.json dentro
        do diretório final.
        """
        try:
            data = self._load_json(final_file)
        except Exception as e:
            self.logger.error(f"Erro ao carregar final_file para gerar versão sem 'analysis': {e}")
            return None

        stripped = []
        for entry in data:
            if isinstance(entry, dict):
                new_e = entry.copy()
                # remover 'analysis' se existir
                if 'analysis' in new_e:
                    new_e.pop('analysis', None)
                # remover 'cleaning_metadata' se existir
                if 'cleaning_metadata' in new_e:
                    new_e.pop('cleaning_metadata', None)
                stripped.append(new_e)
            else:
                stripped.append(entry)

        no_analysis_file = self.dirs['final'] / f'consolidated_dataset{self.timestamp}.json'
        self._save_json(stripped, no_analysis_file)
        self.stats['final_no_analysis_file'] = str(no_analysis_file)
        self.logger.info(f"✅ Arquivo sem 'analysis' e 'cleaning_metadata' criado: {no_analysis_file} ({len(stripped)} entradas)")
        return no_analysis_file
    
    def generate_report(self, final_file: Path, no_analysis_file: Path = None):
        """Gera relatório final do pipeline"""
        self.logger.info("\n" + "="*80)
        self.logger.info("RELATÓRIO FINAL DO PIPELINE")
        self.logger.info("="*80)
        
        report = {
            'pipeline_execution': {
                'start_time': self.stats['start_time'].isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_seconds': (datetime.now() - self.stats['start_time']).total_seconds()
            },
            'input_datasets': {
                'exploration': str(self.exploration_file),
                'exploitation': str(self.exploitation_file),
                'exploration_entries': self.stats['exploration_entries'],
                'exploitation_entries': self.stats['exploitation_entries']
            },
            'comparison_results': self.stats['comparison_results'],
            'validation_results': {
                name: results['stats'] 
                for name, results in self.stats.get('validation_results', {}).items()
            },
            'final_dataset': {
                'file': str(final_file),
                'total_entries': self.stats['final_dataset_size'],
                'no_analysis_file': str(no_analysis_file) if no_analysis_file else self.stats.get('consolidated_dataset')
            }
        }
        
        report_file = self.dirs['final'] / f'pipeline_report_{self.timestamp}.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"\n📊 Resumo:")
        self.logger.info(f"   Duração: {report['pipeline_execution']['duration_seconds']:.2f}s")
        self.logger.info(f"   Dataset final: {self.stats['final_dataset_size']} entradas")
        if no_analysis_file:
            self.logger.info(f"   Dataset final (sem 'analysis'): {no_analysis_file}")
        self.logger.info(f"   Relatório: {report_file}")
        
        return report_file
    
    def run(self) -> Path:
        """Executa o pipeline completo"""
        try:
            
            self._clear_output_dir()
            
            # Criar estrutura
            self._create_directories()
            
            # Passo 1: Comparação
            comparison_files = self.step1_compare_datasets()
            
            # Passo 2: Validação
            validation_results = self.step2_validate_pairs(comparison_files)
            # salvar validation_results em stats para uso posterior/relatório
            self.stats['validation_results'] = validation_results
            
            # Passo 3: Limpeza (agora faz re-validação e atualização)
            cleaned_files = self.step3_clean_excess_gherkin(validation_results)
            
            # Passo 4: Unificação
            final_file = self.step4_merge_final_dataset(validation_results, cleaned_files)
            
            # Nova etapa: gerar dataset sem 'analysis'
            no_analysis_file = self.generate_no_analysis_dataset(final_file)
            
            # Relatório
            report_file = self.generate_report(final_file, no_analysis_file)
            
            self.logger.info("\n" + "="*80)
            self.logger.info("✅ PIPELINE CONCLUÍDO COM SUCESSO")
            self.logger.info("="*80)
            
            return final_file
            
        except Exception as e:
            self.logger.error(f"\n❌ ERRO NO PIPELINE: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise




def main():
    """Função principal"""
    if len(sys.argv) < 3:
        print("Uso: python pipeline.py <exploration.json> <exploitation.json> [output_dir]")
        sys.exit(1)
    
    exploration_file = sys.argv[1]
    exploitation_file = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "./pipeline_output"
    
    # Verificar arquivos de entrada
    if not os.path.exists(exploration_file):
        print(f"❌ Arquivo não encontrado: {exploration_file}")
        sys.exit(1)
    
    if not os.path.exists(exploitation_file):
        print(f"❌ Arquivo não encontrado: {exploitation_file}")
        sys.exit(1)
    
    # Executar pipeline
    pipeline = GherkinPipeline(exploration_file, exploitation_file, output_dir)
    final_file = pipeline.run()
    
    print(f"\n✅ Pipeline concluído!")
    print(f"📁 Dataset final: {final_file}")
    if pipeline.stats.get('final_no_analysis_file'):
        print(f"📁 Dataset final (sem 'analysis'): {pipeline.stats['final_no_analysis_file']}")
    print(f"📂 Todos os arquivos em: {output_dir}")


if __name__ == "__main__":
    main()