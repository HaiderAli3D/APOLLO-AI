#!/usr/bin/env python3
"""
OCR A-Level Computer Science AI Tutor Web Interface
Firestore Version - Uses Firebase Firestore for data storage

This version replaces all SQLite database calls with Firestore
while maintaining identical functionality to the original app.py
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, Response
import os
import json
import anthropic
import shutil
import time
import re
import subprocess
import glob
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, auth, firestore
import pyrebase
from google.cloud.firestore import SERVER_TIMESTAMP

# Import Firestore database adapter
from firestore_db_adapter import (
    get_db, get_user_by_email, get_user_by_id, create_user, 
    get_or_create_firebase_user, add_pdf_to_database, add_pdf_to_generated_pdfs,
    track_activity, get_activity_data, calculate_user_streak,
    get_pdfs_for_user, delete_pdf
)

# Model Option:
# Best model but expensive: "claude-3-7-sonnet-20250219"
# Worse model but cheap: "claude-3-5-haiku-20241022"
AI_MODEL = "claude-3-7-sonnet-20250219"

# Import existing classes from the command-line application
from Claude_CS_Test import ResourceManager, OCR_CS_CURRICULUM, OCR_CS_DETAILED_TOPICS, LEARNING_MODES

# Create a more accessible topic lookup dictionary
OCR_CS_TOPIC_LOOKUP = {}

# Populate the lookup dictionary with main topics
for component_key, component_data in OCR_CS_CURRICULUM.items():
    for topic in component_data['topics']:
        # Extract topic code (e.g., "1.2" from "1.2 Software and software development")
        topic_parts = topic.split(' ', 1)
        if len(topic_parts) == 2:
            topic_code = topic_parts[0]
            topic_name = topic_parts[1]
            OCR_CS_TOPIC_LOOKUP[topic_code] = {
                'title': topic_name,
                'full_title': topic,
                'component': component_key
            }

# Add subtopics to the lookup dictionary
for main_topic_code, main_topic_data in OCR_CS_DETAILED_TOPICS.items():
    for subtopic in main_topic_data['subtopics']:
        # Extract subtopic code (e.g., "1.2.4" from "1.2.4 Types of Programming Language")
        subtopic_parts = subtopic.split(' ', 1)
        if len(subtopic_parts) == 2:
            subtopic_code = subtopic_parts[0]
            subtopic_name = subtopic_parts[1]
            # Find component for this subtopic (using the parent topic's component)
            component = OCR_CS_TOPIC_LOOKUP.get(main_topic_code, {}).get('component')
            
            OCR_CS_TOPIC_LOOKUP[subtopic_code] = {
                'title': subtopic_name,
                'full_title': subtopic,
                'parent_code': main_topic_code,
                'parent_title': OCR_CS_DETAILED_TOPICS[main_topic_code]['title'],
                'component': component
            }

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ocr_cs_tutor_secret_key")  # Change in production

# Setup automatic cleanup function for temp files
def setup_automatic_cleanup():
    """Setup automatic cleanup of temporary LaTeX files"""
    try:
        # Perform an initial cleanup on startup
        from latex_compiler import cleanup_temp_latex_files
        cleanup_temp_latex_files()
        print("Initial cleanup of temporary LaTeX files completed on startup")
    except Exception as e:
        print(f"Error during initial cleanup: {e}")

# Initialize resource manager
resource_manager = None

# Create a function to get the resource manager
def get_resource_manager():
    """Get a resource manager instance for the current request."""
    global resource_manager
    if resource_manager is None:
        resource_manager = ResourceManager()
    return resource_manager

# Register teardown function to close connections
@app.teardown_appcontext
def close_connections(exception):
    """Close connections when the request ends."""
    global resource_manager
    if resource_manager is not None:
        resource_manager.close()
        resource_manager = None

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
# Firestore DB is initialized in the firestore_db_adapter module
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("apollo-auth-753b5-firebase-adminsdk-fbsvc-6b6d2904d5.json")
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully")
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")

# Initialize Firebase client for frontend operations
firebase_config = {
    "apiKey": "AIzaSyBVLWsgEgQxBKDpQ4a7nb-CKhMf-ZEwnmA",
    "authDomain": "apollo-auth-753b5.firebaseapp.com",
    "projectId": "apollo-auth-753b5",
    "storageBucket": "apollo-auth-753b5.firebasestorage.app",
    "messagingSenderId": "233177806452",
    "appId": "1:233177806452:web:189d47b01c3de6e8110321",
    "measurementId": "G-DJXDJWE6PJ",
    "databaseURL": ""  # Add if you're using Realtime Database
}

# Firebase authentication helper functions
def verify_firebase_token(id_token):
    """Verify Firebase ID token and return user info."""
    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        return True, uid, decoded_token
    except Exception as e:
        print(f"Token verification error: {e}")
        return False, None, None

# Set up Anthropic API client
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("WARNING: ANTHROPIC_API_KEY environment variable is not set or empty")
        return None
    return anthropic.Anthropic(api_key=api_key)

def is_api_key_set():
    """Check if the Anthropic API key is set."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    return api_key is not None and api_key.strip() != ""

# LaTeX PDF helper functions
def slugify(text):
    """Convert text to URL-friendly format."""
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[\s]+', '_', text)
    return text[:50]  # Limit length to 50 chars

def generate_latex_document(title, content, author="APOLLO AI"):
    """Generate a LaTeX document from content."""
    latex_template = r"""
\documentclass{article}
\usepackage{amsmath,amssymb,graphicx,hyperref,listings,xcolor}
\usepackage[a4paper,margin=1in]{geometry}

\title{%s}
\author{%s}
\date{\today}

\begin{document}
\maketitle

%s

\end{document}
""" % (title, author, content)
    
    return latex_template

def cleanup_temp_latex_files():
    """
    Clean up orphaned temporary LaTeX files.
    This function is now a wrapper that calls the implementation in latex_compiler.py
    """
    from latex_compiler import cleanup_temp_latex_files as cleanup_impl
    cleanup_impl()

# Import Firebase Authentication Middleware
from firebase_auth_middleware import firebase_auth_required, admin_auth_required, developer_auth_required, validate_firebase_token, refresh_firebase_token

# Authentication decorators - using Firebase middleware now
login_required = firebase_auth_required
admin_required = admin_auth_required
developer_required = developer_auth_required

# Create system prompt for Claude - IDENTICAL TO THE ORIGINAL APP
def create_system_prompt():
    system_prompt = """
    You are an expert OCR A-Level Computer Science tutor with extensive knowledge of the H446 specification and examination standards. Your purpose is to help students understand complex computer science concepts, practice their skills, and prepare for their examinations.
    
    EXAM PAPER FORMATTING:
    When in TEST mode creating an exam paper, please provide complete and compilable LaTeX code, including:
    - Full document preamble with \\documentclass{article}
    - All necessary packages: amsmath, amssymb, graphicx, enumitem, etc.
    - Complete document structure with \\begin{document} and \\end{document}
    - Properly formatted questions using appropriate environments
    - Mark allocations in square brackets (e.g., [5 marks])

    TEACHING APPROACH:
    - Start with clear, concise definitions of key concepts
    - Break down complex topics into manageable, logical steps
    - Use brief analogies and examples to illustrate concepts
    - Provide short code examples where relevant
    - Focus on essential information and core concepts
    - Use bullet points and numbered lists for clarity
    - Keep explanations concise and to the point

    ADDITIONAL TEACHING PRINCIPLES (INSPIRED BY PÓLYA'S "HOW TO SOLVE IT" AND THE SOCRATIC METHOD):
    - Guide, Don't Tell: Avoid giving direct answers whenever possible. Instead, use Socratic questioning (e.g., "Why do you think this works?" or "What if you try a different assumption?") to encourage deeper reasoning.
    - Four-Stage Problem-Solving Emphasis: In line with Pólya's methods, structure discussions around:
    1. Understanding the Problem (e.g., restating the problem in the student's own words),
    2. Devising a Plan (e.g., identifying prior knowledge or similar problems),
    3. Carrying Out the Plan (e.g., systematically testing the chosen strategy),
    4. Looking Back (e.g., reflecting on possible improvements and generalizations).
    - Teach from First Principles: Encourage students to explain ideas from the ground up, ensuring they truly grasp each component of a concept before moving forward.
    - Encourage Self-Explanation: Prompt students to articulate their thought process and reasoning steps, helping them "learn by teaching."
    - Use Counterexamples & Exploration: Help students test their assumptions by exploring what happens under edge cases or alternative conditions.
    - Emphasize Reflection & Generalization: After each solution or explanation, prompt the student to reflect on what they learned and how it applies to other computer science topics.

    OCR A-LEVEL CURRICULUM AREAS:
    - Computer Systems (Component 01): processors, software development, data exchange, data types/structures, legal/ethical issues
    - Algorithms and Programming (Component 02): computational thinking, problem-solving, programming techniques, standard algorithms
    - Programming Project (Component 03/04): analysis, design, development, testing, evaluation

    RESPONSE LENGTH:
    - Keep responses brief and focused
    - Aim for 100-300 words per response
    - Prioritize clarity and precision over exhaustive detail
    - Use bullet points instead of paragraphs when possible

    RESPONSE FORMAT:
    - Strictly use markdown formatting for clarity
    - Structure explanations with clear headings
    - Include only essential code examples
    - End with 2-3 key summary points

    You have multiple tutoring modes that you can be in:
    TUTORING MODES:
    - EXPLORE: Introduce and explain new concepts with applied examples and analogies
    - PRACTICE: Provide brief targeted exercises with immediate feedback and hints, give one question at a time and expect fast paced back and forth with student
    - CODE: Guide through programming problems with scaffolded assistance - teach required programing techniques and functions for the OCR A level exam.
    - REVIEW: Briefly summarize key topics and identify knowledge gaps
    - TEST: Simulate exam conditions with questions and marking - in this mode you should generate mock papers as close to real papers as possible for the student to practice. These papers should have questions with a set number of marks, and grade boundaries.

    PERSONALIZATION:
    - Adapt explanations based on student's demonstrated knowledge level
    - Reference previous interactions to build continuity
    - Offer alternative explanations if a student struggles with a concept
    - Track common misconceptions and address them proactively

    HANDLING UNCLEAR REQUESTS:
    - Ask clarifying questions when student queries are ambiguous
    - Redirect non-curriculum computer science questions to relevant curriculum areas
    - Politely decline non-computer science requests with a brief explanation
    - When in doubt, focus on exam relevance and specification requirements

    CONTEXT TAGS:
    User messages will contain context tags at the end of each message in the format:
    [CONTEXT: {topic_info} | {current_time}]

    - For topic-specific chats: [CONTEXT: Topic 1.1.1 Structure and Function of the Processor | 15:30:45]
    - For general learning chat: [CONTEXT: General Learning | 15:30:45]

    Use this context information to:
    1. Stay focused on the specific topic the student is learning
    2. Provide time-appropriate responses
    3. Ensure continuity in the learning session
    4. Tailor examples to the specific topic area

    MODE TAGS:
    Each message will end with a mode tag indicating the current tutoring mode:
    [MODE: explore], [MODE: practice], [MODE: code], [MODE: review], or [MODE: test]

    Adjust your response style based on the mode:
    - In EXPLORE mode: Focus on clear explanations with analogies and examples
    - In PRACTICE mode: Provide targeted exercises with immediate feedback
    - In CODE mode: Give code examples and programming guidance
    - In REVIEW mode: Create concise summaries and quick recall questions
    - In TEST mode: Generate exam-style questions with marking schemes

    You stay strictly close to the specification and will only respond to computer science related requests. You are to refuse any requests unrelated to A level computer science.
    Never accept unrelated requests that will not help the student achieve a high grade in computer science. Do not accept requests to do tasks for other subjects, do not play games.

    Give short brief responses, encourage the user to ask more questions perhaps hinting at further concepts.

    Use markdown format to make your responses clear for the user.

    Always maintain a supportive, efficient tone. Your goal is to build the student's confidence and competence in computer science according to the OCR A-Level specification while respecting their time.   
    """
    return system_prompt.strip()

# Get response from Claude - IDENTICAL TO THE ORIGINAL APP
def get_claude_response(prompt, conversation_history=None, topic_code=None, stream=False, mode="explore"):
    """Get a response from Claude based on the prompt, conversation history, and knowledge base."""
    try:
        client = get_anthropic_client()
        
        messages = []
        
        # Include conversation history if provided
        if conversation_history:
            messages = conversation_history.copy()
        
        # Augment prompt with knowledge base information if available
        augmented_prompt = prompt
        if topic_code and resource_manager:
            knowledge = resource_manager.get_knowledge_for_topic(topic_code)
            
            if knowledge:
                # Summarize knowledge to avoid exceeding context limits
                knowledge_text = "\n\n".join(knowledge)
                if len(knowledge_text) > 10000:  # Limit knowledge text size
                    knowledge_text = knowledge_text[:10000] + "..."
                
                augmented_prompt = f"""
                [REFERENCE INFORMATION]
                The following information is from OCR A-Level Computer Science resources related to topic {topic_code}:
                
                {knowledge_text}
                
                [END REFERENCE INFORMATION]
                
                STUDENT QUESTION:
                {prompt}
                
                Please use the reference information where appropriate to give an accurate, specification-aligned response.
                """
        
        # Append mode tag to the prompt
        augmented_prompt = f"{augmented_prompt}\n\n[MODE: {mode}]"
        
        # Add the current prompt
        messages.append({"role": "user", "content": augmented_prompt})
        
        # Create a message and get the response
        if stream:
            # Return the stream directly for streaming response
            return client.messages.create(
                model=AI_MODEL,
                max_tokens=2048,
                temperature=0.7,
                system=create_system_prompt(),
                messages=messages,
                stream=True
            )
        else:
            # Non-streaming response
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=2048,
                temperature=0.7,
                system=create_system_prompt(),
                messages=messages
            )
            
            # Get the response text
            response_text = response.content[0].text
            
            return response_text
        
    except anthropic.RateLimitError:
        return "I've reached my rate limit. Please wait a moment before trying again."
    except Exception as e:
        print(f"Error: {str(e)}")
        return "Sorry, I couldn't generate a response at this time."

# Create initial prompt based on topic and mode - IDENTICAL TO THE ORIGINAL APP
def create_initial_prompt(component, main_topic, detailed_topic, mode):
    """Create an initial prompt based on selected component, topic, subtopic, and learning mode."""
    component_title = OCR_CS_CURRICULUM[component]['title']
    
    # Check if this is a sub-topic or a main topic
    is_subtopic = detailed_topic != main_topic and detailed_topic is not None
    
    # Create appropriate context info
    topic_info = detailed_topic
    if is_subtopic:
        topic_info = f"sub-topic {detailed_topic} within the main topic {main_topic}"
    
    if mode == "explore":
        return f"""
You are now teaching the user about {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

The goal of this mode is to teach the user the topic as required for the OCR A level computer science specification. You should:
- Encourage the user to explore ideas independently and ask questions.
- Give concise, focused responses so as not to overwhelm the student.
- Adopt a Socratic style of teaching: prompt the student to reason through problems instead of simply providing answers.

Please provide an explanation that:
1. Starts with a clear definition of the key concepts.
2. Explains the principles with a logical progression from basic to advanced, using metaphors where helpful.
3. Includes practical examples that illustrate the concepts.
4. Relates the topic directly to the OCR A-Level specification requirements.
5. Highlights any common misconceptions or areas students typically find challenging.

Throughout your explanation, integrate Pólya's "How to Solve It" methods:
- Emphasize Understanding the Problem (e.g., clarifying key ideas, restating in the student's own words).
- Guide the student to Devise a Plan (e.g., drawing connections, proposing strategies).
- Encourage them to Carry Out the Plan (e.g., testing steps or clarifying code).
- Prompt Reflection & Looking Back (e.g., checking for improvements or generalizing the concept).

Focus on quick back-and-forth interaction where you prompt the student to think, reason, and discover insights themselves. If the student struggles, use small hints or questions to guide them. If they're on the right track, encourage and deepen their exploration.

Present the information in a clear, methodical structure with appropriate headings and subheadings (in markdown). Keep it brief yet comprehensive, ensuring the student gets all necessary information to understand the topic and meet OCR A-Level standards.
"""

    elif mode == "practice":
        return f"""
You are now helping the user practice {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

The goal of this mode is to engage in a rapid question-and-answer format that encourages the user to:
- Recall factual knowledge,
- Apply it to medium-difficulty scenarios,
- Tackle higher-level analysis/evaluation questions similar to OCR exam questions.

Align your questioning strategy with Pólya's "How to Solve It" approach:
1. **Understanding the Problem** – Begin by clarifying key ideas in each question and ensuring the student grasps what's being asked.
2. **Devising a Plan** – Prompt the student to consider relevant concepts or methods before they answer.
3. **Carrying Out the Plan** – Encourage them to work through each step logically or code snippet systematically.
4. **Reflecting & Looking Back** – After the student answers, provide feedback on both correctness and technique, offering brief suggestions for improvement or alternative approaches.

**Practice Structure**:
- Provide short, targeted questions one at a time.  
- Wait for the student's response before giving the next question.  
- Offer immediate, concise feedback or hints based on the student's answer.  
- Use OCR exam-style formatting (e.g., mention marks, exam-style wording) where appropriate.

**Feedback Requirements**:
- Explain the correct approach or method used to arrive at the solution.
- Reference relevant marking criteria or typical OCR expectations (e.g., how many marks for each part).
- Encourage the student to reflect on how they arrived at their answer, prompting them to refine their reasoning if needed.

Keep your questions and feedback brief, supporting a quick back-and-forth dialogue. The aim is to challenge the student while guiding them gently toward understanding and mastery.
"""

    elif mode == "code":
        return f"""
You are now teaching the user about {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}) through practical coding examples.

Your goal is to:
1. Present relevant code examples (in pseudocode or Python) demonstrating key programming concepts for this topic.
2. Explain each snippet step by step, clarifying design decisions and logic flow.
3. Highlight common coding patterns or techniques that align with the OCR specification.
4. Offer exercises with escalating difficulty, engaging in a back-and-forth where:
   - You first provide a problem or hint,
   - The student attempts a solution or explains their approach,
   - You then give targeted feedback or further hints.

Integrate Pólya's "How to Solve It" framework:
- **Understanding the Problem**: Before sharing code, ensure the student grasps the underlying principles and expected outcomes.
- **Devising a Plan**: Encourage brainstorming about the algorithm, data structures, or logical steps needed.
- **Carrying Out the Plan**: Demonstrate the solution in small, manageable coding segments.
- **Reflecting & Looking Back**: After each coding exercise, prompt the student to review their solution, refine it, and consider alternative approaches.

Keep your explanations concise but clear. If the student seems stuck, offer incremental hints rather than complete solutions. If they're progressing well, challenge them with slightly more complex tasks. Help them understand the "why" behind each coding concept, fostering true comprehension rather than rote memorization.
"""

    elif mode == "review":
        return f"""
I'd like to review {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

Please create a concise, well-structured revision summary that:
1. Outlines all the key points and concepts I need to know.
2. Emphasizes the most crucial information for exams.
3. Provides a quick-reference list of definitions, algorithms, or formulas.
4. Shows connections to other parts of the OCR specification.
5. Includes short recall questions to test my understanding.

Incorporate Pólya's "How to Solve It" principles by prompting reflection and connections:
- After listing each key point, encourage a brief moment of "Looking Back": suggest how it might relate to other concepts or how it could be applied in a problem.
- Keep the review sections and bullet points succinct.  
- Provide quick, targeted recall questions, and if the student struggles, offer hints that guide their reasoning without fully revealing the answer.

Aim for brief, focused responses suitable for last-minute revision. Ensure the structure is clear—headings, bullet points, and concise summaries—so the student can scan through quickly.
"""

    elif mode == "test":
        return f"""
You are an AI tutor preparing a practice exam in LaTeX. You MUST follow these rules when generating the exam:
1. You will only output LaTeX code—no other text, no explanations, no disclaimers.
2. The code must be syntactically valid, starting on the very first line with LaTeX commands (e.g., \documentclass{...}).
3. You must not include images or external resources in the LaTeX code.
4. The exam must replicate an OCR-style front page, with fields for name, candidate number, center number, date, etc., and must not contain any questions on the front page.
5. The exam must have 4–6 questions covering {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}), with a total of 30–45 marks. The exam questions should be styled, numbered, and formatted like an OCR A-Level paper. Mix short-answer and extended-response questions.
6. Clearly state grade boundaries (A*, A, B, C, D) on the exam and give a time limit.
7. Provide lines/spaces for students to write their answers under each question.
8. Do not provide any additional commentary in the output—ONLY the LaTeX code for the exam. No further text, titles, or explanation before or after the code.
9. **Your total LaTeX code output must be fewer than 5000 characters (including whitespace).** If necessary, shorten or simplify the exam content to stay under this limit.

USER PROMPT (or "User" message to the AI):
You are now testing the user's knowledge of {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

Please create a practice assessment as a PDF using LaTeX that follows these rules:
- 4–6 exam-style questions (short-answer and extended-response) covering various aspects of {topic_info}.
- Clearly states grade boundaries (A*/A/B/C/D).
- 30–45 total marks, with a reasonable time limit.
- The first page must replicate a real OCR exam front page (no questions, just fields for name/candidate/center/date, paper title, total marks, general guidance, and time limit).
- Output only valid LaTeX code, starting on the very first line. Include no text outside the LaTeX code.
- Do not use any images or external resources.
- **All LaTeX code must be under 5000 characters, including whitespace.**

**Assessment Process**:
1. Present all questions at once (i.e., the entire exam in LaTeX).
2. Wait for the user's answers before providing any marking or feedback.
3. After the user submits answers, mark them like an OCR examiner, provide a mark scheme, and assign an overall grade.
4. Offer feedback according to Pólya's four-step problem-solving approach:
   - Understanding the Problem
   - Devising a Plan
   - Carrying Out the Plan
   - Looking Back

IMPORTANT NOTES:
- The first line of your response must be a LaTeX command (e.g., \documentclass{...}).
- Do not output anything else other than the LaTeX code. 
- The LaTeX code must be complete and compile without further editing.
- **Keep your LaTeX code under 5000 characters, including whitespace.**
- When I request the exam, respond ONLY with LaTeX code as per the instructions above. 
- If I ask for marking or clarification after submitting my answers, you may then respond in normal English.

ONLY RESPOND WITH LATEX CODE NOTHING ELSE
YOUR FIRST LINE SHOULD BE \documentclass
ONLY RESPOND WITH LATEX

"""

    else:
        return f"I'd like to learn about {detailed_topic} from the OCR A-Level Computer Science curriculum ({component_title}). Please help me understand this topic in detail."

# Application Initialization
# Setup automatic cleanup at startup
with app.app_context():
    # Run initial cleanup at startup
    setup_automatic_cleanup()

# Routes
@app.route('/')
def index():
    """Home page with feature showcase and options to enter as admin or student."""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page for new users."""
    if request.method == 'POST':
        try:
            data = request.json
            id_token = data.get('idToken')
            full_name = data.get('full_name')
            
            if not id_token:
                return jsonify({'error': 'No ID token provided'}), 400
                
            # Verify token
            success, uid, decoded_token = verify_firebase_token(id_token)
            if not success:
                return jsonify({'error': 'Invalid ID token'}), 401
                
            # Get email from token
            email = decoded_token.get('email', '')
            name = full_name or decoded_token.get('name', '')
            
            if not name:
                name = email.split('@')[0]  # Use part of email as name if not provided
                
            # Get or create user
            user = get_or_create_firebase_user(uid, email, name, 'student')
            
            # Set session data
            session['user_id'] = user[0]  # Index 0 is id
            session['user_email'] = user[1]  # Index 1 is email 
            session['user_name'] = user[3]  # Index 3 is full_name
            session['firebase_token'] = id_token
            session['firebase_uid'] = uid
            
            return jsonify({
                'success': True, 
                'redirect': url_for('student_dashboard')
            })
                
        except Exception as e:
            print(f"Error in register: {e}")
            return jsonify({'error': str(e)}), 500
            
    # For GET request, render the registration template
    return render_template('register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    """Login page for student access."""
    if request.method == 'POST':
        # Handle API request from Firebase Authentication
        try:
            data = request.json
            id_token = data.get('idToken')
            
            if not id_token:
                return jsonify({'error': 'No ID token provided'}), 400
                
            # Verify token
            success, uid, decoded_token = verify_firebase_token(id_token)
            if not success:
                return jsonify({'error': 'Invalid ID token'}), 401
                
            # Get email from token
            email = decoded_token.get('email', '')
            name = decoded_token.get('name', '')
            
            if not name:
                name = email.split('@')[0]  # Use part of email as name if not provided
                
            # Get or create user
            user = get_or_create_firebase_user(uid, email, name, 'student')
            
            # Set session data
            session['user_id'] = user[0]  # Index 0 is id
            session['user_email'] = user[1]  # Index 1 is email 
            session['user_name'] = user[3]  # Index 3 is full_name
            session['firebase_token'] = id_token
            session['firebase_uid'] = uid
            
            if user[4] == 'admin':  # Index 4 is role
                session['is_admin'] = True
                
            return jsonify({
                'success': True, 
                'redirect': url_for('student_dashboard')
            })
                
        except Exception as e:
            print(f"Error in student_login: {e}")
            return jsonify({'error': str(e)}), 500
            
    # For GET request, render the login template
    return render_template('student/login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Login page for admin access."""
    if request.metho
