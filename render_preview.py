#!/usr/bin/env python3
"""Quick re-render: build LebenslaufData from cv_example.md and generate PDF."""
import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.document import (
    ApplicationDocuments, AnschreibenData, LebenslaufData,
    CvExperience, CvEducation, CvPublication, CvTalk, CvTool,
)
from pdf.renderer import render_pdf

lebenslauf = LebenslaufData(
    name="Nikkel Blaase",
    email="nikkel.blaase@gmail.com",
    phone="(+49) 178 / 687 44 95",
    location="Bremen",
    website="www.nikkel-blaase.com",
    highlights=[
        "12+ Jahre Product Experience",
        "5+ Jahre Leadership",
        "20+ Companies Served",
        "14M+ Users Reached",
    ],
    skills=[
        "AI", "Agility", "Product Management", "User Experience", "Leadership",
        "Product Thinking", "Product Discovery", "User Interviews", "Product Strategy",
        "Lean Startup", "Business Modelling", "Venture Building", "User Research",
    ],
    education=[
        CvEducation(degree="Bachelor of Arts – Digital Media", institution="University of the Arts (HfK) Bremen", period="2012"),
        CvEducation(degree="Semester abroad", institution="Unitec Auckland, New Zealand", period="2010"),
        CvEducation(degree="Bachelor of Arts – Creative Media", institution="Middlesex University London / SAE", period="2008"),
    ],
    publications=[
        CvPublication(year="2026", title="Produkt Discovery Handbuch", description="Coming soon"),
        CvPublication(year="2023", title="Product Sense", description="Digitales Produktmanagement, 2. Auflage"),
        CvPublication(year="2018", title="Product Discovery bei XING", description="Speaker Interview DL Summit"),
        CvPublication(year="2017", title="Innovation Mindset", description="Article about Corporate Innovation"),
        CvPublication(year="2013", title="Product Thinking", description="Top Article on Medium"),
    ],
    talks=[
        CvTalk(year="2022–heute", title="Trainer: Product Management, AI Engineer, Product Design", description="Digitale Leute, Product Bootcamps"),
        CvTalk(year="2017", title='Mind the Product "Engage" Hamburg', description="Product Discovery Essentials"),
        CvTalk(year="2016", title="Product Management Festival Zurich", description="How to apply Product Thinking"),
    ],
    tools_created=[
        CvTool(year="2016", title="The Unstuck Map", description="A guide for choosing the right framework"),
    ],
    experience=[
        CvExperience(role="Product & AI Lead", company="PERI, Weissenhorn", period="01/2026 – heute", bullets=[
            "Led structured validation and monetization work for two B2B software products.",
            "Established the first end-to-end validation blueprint.",
            "Drove willingness-to-pay and pricing model validation.",
        ]),
        CvExperience(role="Product & AI Lead", company="Pneuhage, Karlsruhe", period="10/2025 – heute", bullets=[
            "Led AI-powered voicebot pilot: 4.2/5 CSAT, ~90% lower call-handling costs.",
            "Cut average call duration from 2.75 min to ~1 min.",
            "Coordinated SAP, Twilio and ElevenLabs integration for 160+ branch rollout.",
        ]),
        CvExperience(role="Product Lead & Tribe Lead", company="Etribes Connect, Hamburg", period="04/2025 – heute", bullets=[
            "Led Product Experts Tribe (1 PM, 2 UX/Service Designers).",
            "Delivered ticketing system, AI voice/chatbot, and e-commerce redesign.",
        ]),
        CvExperience(role="Trainer", company="Digitale Leute School, Cologne", period="09/2022 – heute", bullets=[
            "Taught 500+ participants across Product Management, AI, and Product Design bootcamps.",
            "Average participant NPS of 8.5/10.",
        ]),
        CvExperience(role="Product Lead & Tribe Lead", company="Orbit Ventures, Hamburg", period="09/2020 – 03/2025", bullets=[
            "Led Product Experts Tribe (6 PMs, 2 UX Designers).",
            "Introduced team OKRs and a venture-building framework.",
            "Owner of the Orbit AI toolchain: designed Singularity AI.",
        ]),
        CvExperience(role="Product & Venture Lead", company="Munich Re, Munich", period="11/2022 – 01/2025", bullets=[
            "Led design and development of a digital mental health business.",
            "2.58% ad click-through rate, 23% overall conversion in landing page test.",
            "MVP served 100,000+ end-users with ERGO and HUK-COBURG.",
        ]),
        CvExperience(role="Senior Product Designer", company="XING SE, Hamburg", period="2013 – 2019", bullets=[
            "Shipped constantly to 14M users; increased retention 3x in 1 year (Messenger).",
            "Led 4 major product discoveries resulting in new teams and long-term strategies.",
            "Created instream advertising tech that became a 1.5M € business.",
        ]),
    ],
    languages=["Deutsch (Muttersprache)", "Englisch (fließend)"],
    certifications=[],
)

# Minimal Anschreiben placeholder (just enough for the template)
anschreiben = AnschreibenData(
    sender_name="Nikkel Blaase",
    sender_address="Wilhelm-Dunkering-Weg 52, 28357 Bremen",
    sender_email="nikkel.blaase@gmail.com",
    sender_phone="(+49) 178 / 687 44 95",
    sender_city="Bremen",
    date="14. März 2026",
    company_name="Muster GmbH",
    salutation="Sehr geehrte Damen und Herren,",
    subject="Bewerbung als Product Lead",
    opening_paragraph="Ich bewerbe mich hiermit auf die ausgeschriebene Stelle.",
    body_paragraphs=["[Platzhalter]"],
    closing_paragraph="Ich freue mich auf ein Gespräch.",
    closing_formula="Mit freundlichen Grüßen",
)

docs = ApplicationDocuments(
    anschreiben=anschreiben,
    lebenslauf=lebenslauf,
    language="de",
    job_title="Product Lead",
    company_name="Muster GmbH",
)

out = Path("output/lebenslauf_preview.pdf")
out.parent.mkdir(exist_ok=True)
render_pdf(docs, out)
print(f"PDF gespeichert: {out.resolve()}")
subprocess.run(["open", str(out)], check=True)
