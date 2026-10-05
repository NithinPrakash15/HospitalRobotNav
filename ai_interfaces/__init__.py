"""
HospitalRobotNav — AI Interfaces Package
===========================================
Abstraction layer for AI model integration.

This package provides clean interfaces for:
    - LLM providers (GPT, Gemini, local models)
    - Vision-Language Models (scene understanding)
    - Object Detection (YOLO)
    - QR Code scanning (medicine verification)
    - Patient Identification
    - Electronic Medical Records (EMR / FHIR)

All interfaces use the Strategy pattern — swap implementations without
changing the calling code.
"""
