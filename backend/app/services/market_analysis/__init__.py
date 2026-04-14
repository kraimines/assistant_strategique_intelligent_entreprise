"""Market Analysis Agent — service package.

Sub-modules:
    collector    — fetches raw news (NewsAPI, yfinance, RSS, GNews)
    analyst      — LLM-powered causal relation extraction
    world_model  — Neo4j Knowledge Graph updater
    gnn_predictor — Heterogeneous Temporal GNN for impact prediction
    orchestrator — APScheduler pipeline loop
"""
