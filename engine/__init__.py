"""Quality engine: rule catalogue, static rules, LLM judge, scoring.

Ported from the original CI/CD scanner (scanner/*) and extended so that rules
which were 'manual review' when reading a static solution ZIP become fully
scored when the data is read live from the Dataverse Web API.
"""
