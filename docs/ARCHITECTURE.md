# Architecture and evidence flow

## Candidate serverless path

```mermaid
flowchart LR
    G[Deterministic Generator] --> A[API Gateway]
    A --> I[Ingestion Lambda]
    I --> Q[SQS]
    Q --> T[Transformer Lambda]
    Q -. after retries .-> D[DLQ]
    T --> S3[S3 Event Objects]
    T --> DB[DynamoDB Status Index]
    S3 --> DUCK[DuckDB Rebuild]
    DUCK --> UI[Streamlit Dashboard]
    I --> CW[CloudWatch]
    T --> CW
    Q --> CW
```

## Baseline path

```mermaid
flowchart LR
    G[Same Deterministic Workload Shape] --> F[FastAPI Always-On Container]
    F --> SQ[SQLite]
```

## Evidence path

Raw request traces are written locally at request time. AWS state is then checked through DynamoDB/S3, operational metrics are collected from CloudWatch, negative tests produce JSON evidence contracts, and SHA-256 hashes are generated for the final package.
