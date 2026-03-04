<H1>AI Tool Usage Disclosure</H1>
This project was developed with the assistance of an AI coding tool (ChatGPT). The AI tool was used as a development aid for architectural brainstorming, debugging assistance, and drafting boilerplate code and documentation. <br><br>

All AI-generated content was reviewed, modified where necessary, and validated through manual testing. Final implementation decisions, architectural structure, and debugging steps were determined and executed by the author.

<H2>Scope of AI Assistance</H2>
AI was used in the following areas:
<H4> 1. Architectural Planning </H4>
AI assisted in: <br>
 ⁃ Proposing a layered architecture (Webhook → Service Layer → Middleware API → CRM Adapter). <br>
 ⁃ Identifying appropriate separation of concerns. <br>
 ⁃ Suggesting safe refactoring sequences. <br>
<br>Final architectural decisions (including incremental migration instead of a full rewrite) were made independently to reduce regression risk.

<H4> 2. Boilerplate Generation </H4>
 AI was used to draft initial versions of: <br>

• Middleware API endpoints: <br>
   ⁃ &nbsp;&nbsp;&nbsp; POST /api/leads <br>
   ⁃ &nbsp;&nbsp;&nbsp; GET /api/leads/{id} <br>
   ⁃ &nbsp;&nbsp;&nbsp; PATCH /api/leads/{id} <br>
   ⁃ &nbsp;&nbsp;&nbsp; GET /api/leads <br>
   ⁃ &nbsp;&nbsp;&nbsp; POST /api/calls/{call_id}/summary <br>
• API key authentication decorator <br>
• HubSpot upsert adapter structure <br>
Documentation templates (README, integration guide)
All generated code was manually reviewed, integrated, and tested before use.
