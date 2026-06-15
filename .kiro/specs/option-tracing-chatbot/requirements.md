# Requirements Document

## Introduction

This document specifies the requirements for a WhatsApp chatbot that delivers adaptive math assessments to university students using Option Tracing — a Knowledge Tracing variant that maps each wrong answer option to a specific misconception. The system extends Bayesian Knowledge Tracing (BKT) with misconception probabilities, enabling targeted feedback and diagnostic output for thesis research. The baseline prototype covers 3 math skills with plain-text questions delivered via WhatsApp, with future multi-platform support planned.

## Glossary

- **Chatbot**: The WhatsApp-based conversational agent that presents questions and processes student responses
- **Option_Tracing_Engine**: The core computational module that maps selected answer options to misconceptions, tracks misconception patterns, and computes mastery/misconception probabilities using an extended BKT model
- **Session_Manager**: The module responsible for maintaining conversation state per student including current question, attempt count, and flow position within Redis
- **Question_Bank**: The PostgreSQL-stored collection of multiple-choice questions where each distractor is pre-mapped to a specific misconception
- **Misconception**: A specific, identifiable error in mathematical reasoning that corresponds to a particular wrong answer option
- **Knowledge_Component (KC)**: A discrete mathematical skill or concept within the KC graph (baseline: 3 skills)
- **Verification_Question**: A question similar to the original that tests whether the student has corrected the identified misconception after receiving feedback
- **Mastery_Probability (P(mastery))**: The BKT-computed probability that a student has mastered a specific Knowledge Component
- **Learning_Rate (P(transition))**: The BKT transition probability representing how quickly a student acquires a skill
- **Misconception_Probability (P(misconception))**: The Option Tracing-computed probability that a student holds a specific misconception about a Knowledge Component
- **Webhook_Server**: The FastAPI application that receives incoming WhatsApp messages and sends responses via the WhatsApp Cloud API
- **Feedback_Generator**: The module that retrieves and formats misconception-specific explanations and correct solution methods
- **Analytics_Module**: The module responsible for aggregating interaction data and exporting research datasets for thesis analysis
- **Messaging_Gateway**: The abstraction layer over platform-specific APIs (WhatsApp Cloud API, Telegram Bot API, Discord API) that normalizes incoming/outgoing messages
- **Conversation_Window**: The 24-hour period after a user-initiated message during which the Chatbot can freely respond via WhatsApp without template messages

## Requirements

### Requirement 1: Question Delivery

**User Story:** As a student, I want to receive multiple-choice math questions via WhatsApp, so that I can practice and be assessed on my mathematical skills.

#### Acceptance Criteria

1. WHEN a student sends any message to the Chatbot and has an active session with a pending Knowledge_Component, THE Chatbot SHALL present a multiple-choice question from the Question_Bank for the current Knowledge_Component
2. THE Chatbot SHALL format each question as plain text with the question stem followed by labeled options (A, B, C, D), each on a separate line
3. THE Chatbot SHALL accept student responses as a single letter (A, B, C, or D) in either uppercase or lowercase, ignoring leading and trailing whitespace
4. IF a student sends an unrecognized response, THEN THE Chatbot SHALL prompt the student to reply with a valid option letter (A, B, C, or D) without consuming an attempt
5. WHEN a student answers correctly on any attempt, THE Chatbot SHALL acknowledge the correct answer and proceed to the next Knowledge_Component in the KC graph
6. WHEN a student answers correctly and no remaining Knowledge_Components exist in the KC graph, THE Chatbot SHALL display a completion message indicating the assessment is finished

### Requirement 2: Option Tracing and Misconception Detection

**User Story:** As a researcher, I want the system to identify which specific misconception a student holds based on the wrong option they select, so that I can provide targeted remediation and collect diagnostic data.

#### Acceptance Criteria

1. THE Question_Bank SHALL store a mapping from each distractor option to exactly one Misconception for every question
2. WHEN a student selects a wrong option, THE Option_Tracing_Engine SHALL identify the corresponding Misconception from the question's distractor-misconception mapping
3. WHEN a student selects a wrong option, THE Option_Tracing_Engine SHALL record the selected option, the identified Misconception, the attempt number, the student identifier, the question identifier, and a timestamp to the student interaction log
4. WHEN a student completes all attempts on a single question, THE Option_Tracing_Engine SHALL classify the misconception pattern as "consistent" if the same Misconception was selected in at least 2 out of the total wrong attempts, or as "varied" if no single Misconception accounts for at least 2 selections
5. IF a student selects different Misconceptions with equal frequency across attempts (e.g., each Misconception selected exactly once), THEN THE Option_Tracing_Engine SHALL designate the Misconception from the most recent wrong attempt as the dominant Misconception

### Requirement 3: Retry Logic

**User Story:** As a student, I want multiple chances to answer a question correctly, so that I can self-correct before receiving explicit feedback.

#### Acceptance Criteria

1. WHEN a student answers incorrectly on attempt 1 or attempt 2, THE Chatbot SHALL inform the student the answer is incorrect, indicate the number of remaining attempts, and re-present the same question with identical options
2. THE Session_Manager SHALL track the attempt count per question, allowing a maximum of 3 attempts before triggering the feedback phase; invalid responses (unrecognized input) SHALL NOT increment the attempt counter
3. WHEN a student answers incorrectly on attempt 3, THE Chatbot SHALL transition to the feedback phase instead of re-presenting the question
4. WHILE a student is in the retry phase, THE Session_Manager SHALL preserve the current question context including question identifier, all previously selected options with their corresponding attempt numbers, and the current attempt count

### Requirement 4: Misconception-Specific Feedback

**User Story:** As a student, I want targeted feedback explaining my specific error in thinking after failing a question, so that I can correct my misconception and learn the proper approach.

#### Acceptance Criteria

1. WHEN the student exhausts all 3 attempts, THE Feedback_Generator SHALL deliver feedback specific to the dominant Misconception detected across the attempts within the same response message as the final incorrect-answer acknowledgment
2. THE Feedback_Generator SHALL structure feedback as a single plain-text message with three sequential components: (a) identification of the Misconception by name and description, (b) explanation of why the reasoning is incorrect, (c) the correct method of solving with step-by-step working
3. THE Feedback_Generator SHALL retrieve the feedback content from the misconception-specific text stored in the Question_Bank
4. WHEN a student selects different misconceptions across attempts, THE Feedback_Generator SHALL deliver feedback for the most frequently selected Misconception; IF two or more Misconceptions are selected with equal frequency, THEN THE Feedback_Generator SHALL deliver feedback for the Misconception selected on the most recent attempt
5. IF the Question_Bank does not contain feedback text for the identified Misconception, THEN THE Feedback_Generator SHALL deliver a generic feedback message indicating the correct answer and correct solving method for the question without misconception-specific explanation

### Requirement 5: Verification Phase

**User Story:** As a researcher, I want to verify whether feedback successfully corrected the misconception, so that I can measure the effectiveness of targeted remediation.

#### Acceptance Criteria

1. WHEN the feedback phase completes, THE Chatbot SHALL present exactly 1 Verification_Question that tests the same Knowledge_Component and targets the same Misconception, within the same message sequence as the feedback delivery
2. WHEN the student answers the Verification_Question correctly, THE Chatbot SHALL display a mastery confirmation message ("Selamat sudah mahir"), mark the Knowledge_Component as mastered for that student, and proceed to the next Knowledge_Component in the KC graph
3. WHEN the student answers the Verification_Question incorrectly, THE Chatbot SHALL set the Knowledge_Component status to "needs_review" in the student's mastery record and end the assessment for that skill without offering additional attempts
4. THE Verification_Question SHALL be a different question from the original but shall test the same Knowledge_Component and contain distractors mapped to the same set of Misconceptions
5. THE Chatbot SHALL allow the student exactly 1 attempt to answer the Verification_Question, with no retry opportunities regardless of the response
6. IF no Verification_Question targeting the required Knowledge_Component and Misconception exists in the Question_Bank, THEN THE Chatbot SHALL log the missing question event and skip verification by setting the Knowledge_Component status to "needs_review"

### Requirement 6: BKT Model Computation

**User Story:** As a researcher, I want the system to compute mastery probability, learning rate, and misconception probability per student per skill, so that I can produce the diagnostic output required for thesis analysis.

#### Acceptance Criteria

1. THE Option_Tracing_Engine SHALL compute P(mastery) per student per Knowledge_Component using the BKT framework with the pre-calibrated P(L₀), P(guess), and P(slip) values provided as initial parameters, producing a probability value between 0.0 and 1.0
2. THE Option_Tracing_Engine SHALL compute P(transition) (learning rate) per student per Knowledge_Component based on observed response sequences, producing a probability value between 0.0 and 1.0
3. THE Option_Tracing_Engine SHALL compute P(misconception) per student per Knowledge_Component per Misconception based on the option selection history, producing a probability value between 0.0 and 1.0
4. WHEN a student completes an interaction (correct answer, incorrect answer on any retry attempt, verification pass, or verification fail), THE Option_Tracing_Engine SHALL update all three probability estimates for the relevant Knowledge_Component within 2 seconds of the interaction being recorded
5. THE Option_Tracing_Engine SHALL use the pre-defined KC graph to determine prerequisite relationships between Knowledge_Components for selecting the next Knowledge_Component to assess
6. WHEN a new student is registered, THE Option_Tracing_Engine SHALL initialize P(mastery) using the pre-calibrated P(L₀) value, P(transition) using the pre-calibrated initial learning rate, and P(misconception) to 0.0 for all Misconceptions associated with each Knowledge_Component

### Requirement 7: Session State Management

**User Story:** As a student, I want my conversation progress to be maintained throughout a session, so that I do not lose my place if there are delays in responding.

#### Acceptance Criteria

1. THE Session_Manager SHALL store conversation state in Redis including: current Knowledge_Component, current question, attempt count, flow phase (question/retry/feedback/verification), and selected options history
2. WHILE a session is active, THE Session_Manager SHALL maintain state for the duration of the WhatsApp Conversation_Window (24 hours)
3. WHEN a session expires due to the Conversation_Window closing, THE Session_Manager SHALL persist the student's progress to PostgreSQL so that the next session resumes from the correct Knowledge_Component
4. IF Redis becomes unavailable, THEN THE Webhook_Server SHALL return a graceful error message to the student and log the failure for operational monitoring

### Requirement 8: WhatsApp Webhook Integration

**User Story:** As a system operator, I want a reliable webhook server that processes WhatsApp messages, so that students can interact with the chatbot through their familiar messaging platform.

#### Acceptance Criteria

1. THE Webhook_Server SHALL expose an HTTP endpoint that receives incoming messages from the WhatsApp Cloud API via webhook POST requests
2. THE Webhook_Server SHALL validate incoming webhook payloads using the verification token and signature provided by the WhatsApp Cloud API
3. THE Webhook_Server SHALL respond to webhook verification (GET) requests with the correct challenge response for initial endpoint registration
4. WHEN a valid message is received, THE Webhook_Server SHALL process the message and send a response back via the WhatsApp Cloud API within 5 seconds to avoid message delivery timeout
5. IF the Webhook_Server receives a duplicate message (same message ID), THEN THE Webhook_Server SHALL ignore the duplicate and respond with HTTP 200 without reprocessing

### Requirement 9: Data Storage and Question Bank

**User Story:** As a researcher, I want structured storage for questions, misconception mappings, and student interaction data, so that I can analyze learning patterns and validate the Option Tracing model.

#### Acceptance Criteria

1. THE Question_Bank SHALL store each question with: question text, correct option, all distractor options, the Knowledge_Component it belongs to, and a mapping of each distractor to its corresponding Misconception
2. THE Question_Bank SHALL store misconception records with: misconception identifier, associated Knowledge_Component, description, feedback text explaining the error, and the correct reasoning explanation
3. THE Question_Bank SHALL store student interaction records with: student identifier, question identifier, attempt number, selected option, identified Misconception, timestamp, and session identifier
4. THE Question_Bank SHALL store student mastery records with: student identifier, Knowledge_Component identifier, current P(mastery), current P(transition), P(misconception) per misconception, and last activity timestamp
5. THE Question_Bank SHALL support the 3 Knowledge_Components defined in the baseline KC graph with their associated questions and misconception mappings

### Requirement 10: Analytics and Research Data Export

**User Story:** As a researcher, I want to export structured interaction data and computed probabilities, so that I can perform thesis analysis on the Option Tracing model's effectiveness.

#### Acceptance Criteria

1. THE Analytics_Module SHALL export per-student learning trajectories including all interaction records ordered by timestamp
2. THE Analytics_Module SHALL export population-level misconception frequency data showing which Misconceptions are most prevalent per Knowledge_Component
3. THE Analytics_Module SHALL export the computed diagnostic outputs (P(mastery), P(transition), P(misconception)) for all students across all Knowledge_Components
4. THE Analytics_Module SHALL provide data export in CSV format suitable for statistical analysis tools
5. WHEN a data export is requested, THE Analytics_Module SHALL include only anonymized student identifiers to comply with research ethics requirements

### Requirement 11: Multi-Platform Messaging Abstraction

**User Story:** As a system operator, I want the messaging layer to be platform-agnostic, so that the system can be extended to Telegram and Discord in the future without modifying the core assessment logic.

#### Acceptance Criteria

1. THE Messaging_Gateway SHALL provide a unified interface for receiving messages and sending responses regardless of the underlying platform (WhatsApp, Telegram, Discord)
2. THE Messaging_Gateway SHALL normalize incoming messages from any platform into a common format containing: sender identifier, message text, and platform identifier
3. THE Messaging_Gateway SHALL format outgoing messages according to each platform's text formatting capabilities while maintaining equivalent content
4. WHILE only WhatsApp is active in the baseline deployment, THE Messaging_Gateway SHALL be structured so that adding a new platform requires implementing only the platform-specific adapter without changes to the Option_Tracing_Engine, Feedback_Generator, or Session_Manager

### Requirement 12: Student Identification and Registration

**User Story:** As a student, I want the system to recognize me across sessions using my WhatsApp number, so that my progress and mastery state are preserved over time.

#### Acceptance Criteria

1. WHEN a new phone number sends a message for the first time, THE Chatbot SHALL register the student using their WhatsApp phone number as the unique identifier and initialize mastery probabilities using the pre-calibrated P(L₀) values
2. WHEN a previously registered student sends a message, THE Session_Manager SHALL load their existing mastery state and resume from the appropriate Knowledge_Component
3. THE Chatbot SHALL store phone numbers in hashed form in the database to protect student privacy while maintaining session continuity
