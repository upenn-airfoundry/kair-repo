from enrichment.iterative_enrichment import process_next_task, iterative_enrichment
from enrichment.seed_lists import consult_person_seeds
from entities.generate_doc_info import parse_files_and_index

from apscheduler.schedulers.tornado import TornadoScheduler

class EnrichmentDaemon:
    @classmethod
    def initialize_enrichment(cls, graph_accessor):
        cls.scheduler = TornadoScheduler()
        cls.graph_accessor = graph_accessor
        cls.scheduler.configure(timezone="US/Eastern")
        cls.scheduler.add_job(lambda: consult_person_seeds(graph_accessor))
        cls.scheduler.add_job(lambda: process_next_task(graph_accessor), 'interval', seconds=30, max_instances=1)
        cls.scheduler.start()

    @classmethod
    def stop_enrichment(cls):
        if cls.scheduler:
            cls.scheduler.shutdown()
            
    @classmethod
    def add_enrichment_task(cls, name:str, prompt:str, scope:str, promise:str):
        if cls.graph_accessor is None:
            raise ValueError("EnrichmentDaemon not initialized with a GraphAccessor.")
        
        criterion_id = cls.graph_accessor.add_assessment_criterion(name, prompt, scope, promise)

        if cls.scheduler:
            iterative_enrichment(cls.graph_accessor, name)
        
        return criterion_id

    @classmethod
    def run_enrichment_task(cls, name:str):
        if cls.graph_accessor is None:
            raise ValueError("EnrichmentDaemon not initialized with a GraphAccessor.")
        
        if cls.scheduler:
            iterative_enrichment(cls.graph_accessor, name)
        
            return True
        else:
            return False
        
    @classmethod
    async def parse_and_index_file(cls, use_aryn: bool = False):
        if cls.graph_accessor is None:
            raise ValueError("EnrichmentDaemon not initialized with a GraphAccessor.")
        
        await parse_files_and_index(use_aryn)