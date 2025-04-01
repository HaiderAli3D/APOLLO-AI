#!/usr/bin/env python3
"""
OCR A-Level Computer Science AI Tutor Web Interface

"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, Response
import os
import json
import anthropic
import sqlite3
import hashlib
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
from firebase_admin import credentials, auth
import pyrebase

# Model Option:
# Best model but expensive: "claude-3-7-sonnet-20250219"
# Worse model but cheap: "claude-3-5-haiku-20241022"
AI_MODEL = "claude-3-7-sonnet-20250219"

# Import existing classes from the command-line application
from Claude_CS_Test import ResourceManager, OCRCSDatabase, OCR_CS_CURRICULUM, OCR_CS_DETAILED_TOPICS, LEARNING_MODES

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

# Initialize resource manager and database
# We'll create these per request to avoid thread safety issues with SQLite
resource_manager = None
db = None

# Create a function to get the resource manager
def get_resource_manager():
    """Get a resource manager instance for the current request."""
    global resource_manager
    if resource_manager is None:
        resource_manager = ResourceManager()
    return resource_manager

# Create a function to get the database
def get_db():
    """Get a database instance for the current request."""
    global db
    if db is None:
        db = OCRCSDatabase()
        
        # Add monkey patching for basic OCRCSDatabase class to support user verification
        if not hasattr(db, 'verify_session_ownership'):
            def verify_session_ownership(self, session_id, user_id):
                """Check if a session belongs to a user - basic implementation always returns True."""
                return True
            db.verify_session_ownership = verify_session_ownership.__get__(db)
    
    return db

# Register teardown function to close connections
@app.teardown_appcontext
def close_connections(exception):
    """Close database connections when the request ends."""
    global resource_manager, db
    if resource_manager is not None:
        resource_manager.close()
        resource_manager = None
    if db is not None:
        db.close()
        db = None

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
try:
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

def get_or_create_firebase_user(uid, email, full_name, role='student', profile_picture_url=None, decoded_token=None):
    """Get existing user by Firebase UID or create a new one."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Get profile picture from token if not provided explicitly
    if profile_picture_url is None and decoded_token:
        # Check if token has picture URL (common with Google authentication)
        profile_picture_url = decoded_token.get('picture', None)
        
        # Check Firebase provider
        provider = decoded_token.get('firebase', {}).get('sign_in_provider', '')
        if provider == 'google.com' and not profile_picture_url:
            # Try alternative picture field that might be present in Google auth
            profile_picture_url = decoded_token.get('photoURL', None)
    
    # Check if user exists by Firebase UID
    cursor.execute("SELECT * FROM users WHERE firebase_uid = ?", (uid,))
    user = cursor.fetchone()
    
    if user:
        # User exists, update profile picture if provided
        if profile_picture_url:
            cursor.execute(
                "UPDATE users SET profile_picture_url = ? WHERE id = ?",
                (profile_picture_url, user[0])
            )
            conn.commit()
            
            # Refresh user data
            cursor.execute("SELECT * FROM users WHERE id = ?", (user[0],))
            user = cursor.fetchone()
            
        conn.close()
        return user
    
    # Check if user exists by email (for migration)
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if user:
        # Update existing user with Firebase UID and profile picture
        update_query = "UPDATE users SET firebase_uid = ?, account_migrated = 1"
        params = [uid, user[0]]
        
        if profile_picture_url:
            update_query += ", profile_picture_url = ?"
            params.insert(1, profile_picture_url)
            
        update_query += " WHERE id = ?"
        
        cursor.execute(update_query, params)
        conn.commit()
        
        # Refresh user data
        cursor.execute("SELECT * FROM users WHERE id = ?", (user[0],))
        user = cursor.fetchone()
        
        conn.close()
        return user
    
    # Create new user
    insert_query = "INSERT INTO users (email, password_hash, full_name, role, firebase_uid, account_migrated"
    values = [email, "firebase_auth", full_name, role, uid, 1]
    
    if profile_picture_url:
        insert_query += ", profile_picture_url"
        values.append(profile_picture_url)
        
    insert_query += ") VALUES (" + ", ".join(["?"] * len(values)) + ")"
    
    cursor.execute(insert_query, values)
    conn.commit()
    user_id = cursor.lastrowid
    
    # Get the created user
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    return user

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

def cleanup_old_pdfs(user_id):
    """Remove old PDF files if a user has more than 10 saved."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Get all PDFs for the user, ordered by creation date (oldest first)
    cursor.execute(
        "SELECT id, filename FROM latex_pdfs WHERE user_id = ? ORDER BY created_at ASC", 
        (user_id,)
    )
    pdfs = cursor.fetchall()
    
    # If there are more than 10 PDFs, delete the oldest ones
    if len(pdfs) > 10:
        to_delete = pdfs[:-10]  # Keep the 10 newest PDFs
        
        for pdf_id, filename in to_delete:
            # Delete the file
            filepath = os.path.join('temp_latex', filename)
            pdf_filepath = filepath[:-4] + '.pdf'  # Replace .tex with .pdf
            
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                if os.path.exists(pdf_filepath):
                    os.remove(pdf_filepath)
            except Exception as e:
                print(f"Error deleting file {filename}: {e}")
            
            # Delete the database record
            cursor.execute("DELETE FROM latex_pdfs WHERE id = ?", (pdf_id,))
    
    conn.commit()
    conn.close()

def cleanup_temp_latex_files():
    """
    Clean up orphaned temporary LaTeX files.
    This function is now a wrapper that calls the implementation in latex_compiler.py
    """
    from latex_compiler import cleanup_temp_latex_files as cleanup_impl
    cleanup_impl()

def add_pdf_to_database(user_id, topic_code, topic_title, filename):
    """
    DEPRECATED: Use the generated_pdfs table instead.
    Legacy function for backward compatibility.
    """
    print("Warning: Using deprecated add_pdf_to_database function. Use generated_pdfs table instead.")
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO latex_pdfs (user_id, topic_code, topic_title, filename) VALUES (?, ?, ?, ?)",
            (user_id, topic_code, topic_title, filename)
        )
        conn.commit()
        pdf_id = cursor.lastrowid
    except Exception as e:
        conn.rollback()
        pdf_id = None
        print(f"Error adding PDF to database: {e}")
    finally:
        conn.close()
    
    return pdf_id

# Database functions for user management
def init_user_db():
    """Initialize the user database tables if they don't exist."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT CHECK(role IN ('student', 'admin', 'developer')) DEFAULT 'student',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        firebase_uid TEXT,
        account_migrated BOOLEAN DEFAULT 0
    )
    ''')
    
    # Create generated_pdfs table for storing LaTeX PDFs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS generated_pdfs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        topic_code TEXT NOT NULL,
        title TEXT NOT NULL,
        latex_content TEXT NOT NULL,
        pdf_path TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')
    
    # Modify sessions table to include user_id if it exists
    cursor.execute("PRAGMA table_info(sessions)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    
    if 'user_id' not in column_names and columns:
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)")
        except sqlite3.Error as e:
            print(f"Error modifying sessions table: {e}")
            
    # Create latex_pdfs table for storing generated PDFs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS latex_pdfs (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        topic_code TEXT NOT NULL,
        topic_title TEXT NOT NULL,
        filename TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')
    
    conn.commit()
    conn.close()

def get_user_by_email(email):
    """Get a user from the database by email."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_id(user_id):
    """Get a user from the database by ID."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(email, password, full_name, role='student'):
    """Create a new user in the database."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Check if user already exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False, "Email already registered"
    
    # Hash the password before storing
    password_hash = generate_password_hash(password)
    
    try:
        cursor.execute(
            "INSERT INTO users (email, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (email, password_hash, full_name, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return True, user_id
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)

# Import Firebase Authentication Middleware
from firebase_auth_middleware import firebase_auth_required, admin_auth_required, developer_auth_required, validate_firebase_token, refresh_firebase_token

# Authentication decorators - using Firebase middleware now
login_required = firebase_auth_required
admin_required = admin_auth_required
developer_required = developer_auth_required

# Create system prompt for Claude
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

    ADDITIONAL TEACHING PRINCIPLES (INSPIRED BY PÓLYA’S "HOW TO SOLVE IT" AND THE SOCRATIC METHOD):
    - Guide, Don’t Tell: Avoid giving direct answers whenever possible. Instead, use Socratic questioning (e.g., “Why do you think this works?” or “What if you try a different assumption?”) to encourage deeper reasoning.
    - Four-Stage Problem-Solving Emphasis: In line with Pólya’s methods, structure discussions around:
    1. Understanding the Problem (e.g., restating the problem in the student’s own words),
    2. Devising a Plan (e.g., identifying prior knowledge or similar problems),
    3. Carrying Out the Plan (e.g., systematically testing the chosen strategy),
    4. Looking Back (e.g., reflecting on possible improvements and generalizations).
    - Teach from First Principles: Encourage students to explain ideas from the ground up, ensuring they truly grasp each component of a concept before moving forward.
    - Encourage Self-Explanation: Prompt students to articulate their thought process and reasoning steps, helping them “learn by teaching.”
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

# Get response from Claude
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

# Create initial prompt based on topic and mode
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

Throughout your explanation, integrate Pólya’s “How to Solve It” methods:
- Emphasize Understanding the Problem (e.g., clarifying key ideas, restating in the student’s own words).
- Guide the student to Devise a Plan (e.g., drawing connections, proposing strategies).
- Encourage them to Carry Out the Plan (e.g., testing steps or clarifying code).
- Prompt Reflection & Looking Back (e.g., checking for improvements or generalizing the concept).

Focus on quick back-and-forth interaction where you prompt the student to think, reason, and discover insights themselves. If the student struggles, use small hints or questions to guide them. If they’re on the right track, encourage and deepen their exploration.

Present the information in a clear, methodical structure with appropriate headings and subheadings (in markdown). Keep it brief yet comprehensive, ensuring the student gets all necessary information to understand the topic and meet OCR A-Level standards.
"""

    elif mode == "practice":
        return f"""
You are now helping the user practice {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

The goal of this mode is to engage in a rapid question-and-answer format that encourages the user to:
- Recall factual knowledge,
- Apply it to medium-difficulty scenarios,
- Tackle higher-level analysis/evaluation questions similar to OCR exam questions.

Align your questioning strategy with Pólya’s “How to Solve It” approach:
1. **Understanding the Problem** – Begin by clarifying key ideas in each question and ensuring the student grasps what’s being asked.
2. **Devising a Plan** – Prompt the student to consider relevant concepts or methods before they answer.
3. **Carrying Out the Plan** – Encourage them to work through each step logically or code snippet systematically.
4. **Reflecting & Looking Back** – After the student answers, provide feedback on both correctness and technique, offering brief suggestions for improvement or alternative approaches.

**Practice Structure**:
- Provide short, targeted questions one at a time.  
- Wait for the student’s response before giving the next question.  
- Offer immediate, concise feedback or hints based on the student’s answer.  
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

Integrate Pólya’s “How to Solve It” framework:
- **Understanding the Problem**: Before sharing code, ensure the student grasps the underlying principles and expected outcomes.
- **Devising a Plan**: Encourage brainstorming about the algorithm, data structures, or logical steps needed.
- **Carrying Out the Plan**: Demonstrate the solution in small, manageable coding segments.
- **Reflecting & Looking Back**: After each coding exercise, prompt the student to review their solution, refine it, and consider alternative approaches.

Keep your explanations concise but clear. If the student seems stuck, offer incremental hints rather than complete solutions. If they’re progressing well, challenge them with slightly more complex tasks. Help them understand the “why” behind each coding concept, fostering true comprehension rather than rote memorization.
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

Incorporate Pólya’s “How to Solve It” principles by prompting reflection and connections:
- After listing each key point, encourage a brief moment of “Looking Back”: suggest how it might relate to other concepts or how it could be applied in a problem.
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
You are now testing the user’s knowledge of {topic_info} from the OCR A-Level Computer Science curriculum ({component_title}).

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
2. Wait for the user’s answers before providing any marking or feedback.
3. After the user submits answers, mark them like an OCR examiner, provide a mark scheme, and assign an overall grade.
4. Offer feedback according to Pólya’s four-step problem-solving approach:
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

# Routes
# Initialize database on startup
def initialize_db():
    """Initialize database tables"""
    init_user_db()

# Function to migrate database schema
def migrate_database():
    """Apply database migrations to add new columns to existing tables"""
    print("Running database migrations...")
    try:
        conn = sqlite3.connect('ocr_cs_tutor.db')
        cursor = conn.cursor()
        
        # Check if user_id column exists in topic_progress table
        cursor.execute("PRAGMA table_info(topic_progress)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'user_id' not in column_names and columns:
            print("Adding user_id column to topic_progress table")
            cursor.execute("ALTER TABLE topic_progress ADD COLUMN user_id INTEGER")
        
        # Check if user_id column exists in sessions table
        cursor.execute("PRAGMA table_info(sessions)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'user_id' not in column_names and columns:
            print("Adding user_id column to sessions table")
            cursor.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER")
        
        # Check if user_id column exists in exam_practice table
        cursor.execute("PRAGMA table_info(exam_practice)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'user_id' not in column_names and columns:
            print("Adding user_id column to exam_practice table")
            cursor.execute("ALTER TABLE exam_practice ADD COLUMN user_id INTEGER")
        
        conn.commit()
        conn.close()
        print("Database migrations completed successfully")
    except sqlite3.Error as e:
        print(f"Database migration error: {e}")

# Create initialization function for database
with app.app_context():
    initialize_db()
    migrate_database()
    # Run initial cleanup at startup
    setup_automatic_cleanup()

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
    if request.method == 'POST':
        # Check if it's a JSON request (Firebase auth)
        if request.is_json:
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
                    name = email.split('@')[0]
                
                # Only allow specific admin emails with Firebase
                if email != 'mr.haider.sm.ali@gmail.com' and not email.endswith('@admin.ocrcstutor.com'):
                    return jsonify({'error': 'This account does not have admin privileges'}), 403
                
                # Get or create admin user
                user = get_or_create_firebase_user(uid, email, name, 'admin')
                
                # Set session data
                session['user_id'] = user[0]
                session['user_email'] = user[1] 
                session['user_name'] = user[3]
                session['is_admin'] = True
                session['firebase_token'] = id_token
                session['firebase_uid'] = uid
                
                # Check if user is also a developer
                if user[4] == 'developer':
                    session['is_developer'] = True
                
                return jsonify({
                    'success': True, 
                    'redirect': url_for('admin_dashboard')
                })
            except Exception as e:
                print(f"Error in admin_login: {e}")
                return jsonify({'error': str(e)}), 500
        else:
            # Traditional form-based login
            email = request.form.get('email')
            password = request.form.get('password')
            
            if not email or not password:
                flash('Email and password are required', 'error')
                return render_template('login.html')
                
            # Special handling for the default admin email
            if email == 'mr.haider.sm.ali@gmail.com':
                # Check if user already exists
                user = get_user_by_email(email)
                
                if not user:
                    # Create new admin if user doesn't exist
                    success, user_id = create_user(email, password, 'Admin User', 'admin')
                    if success:
                        session['user_id'] = user_id
                        session['user_email'] = email
                        session['user_name'] = 'Admin User'
                        session['is_admin'] = True
                        flash('Admin account created successfully', 'success')
                        return redirect(url_for('admin_dashboard'))
                else:
                    # For existing user, verify password and update role if needed
                    if check_password_hash(user[2], password):
                        session['user_id'] = user[0]
                        session['user_email'] = email
                        session['user_name'] = user[3]
                        session['is_admin'] = True
                        
                        # Update role to admin if not already
                        conn = sqlite3.connect('user_database.db')
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user[0],))
                        conn.commit()
                        conn.close()
                        
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('Invalid password', 'error')
                        return render_template('login.html')
            
            # Standard login for other users
            user = get_user_by_email(email)
            
            # Verify user exists, password is correct
            if user and check_password_hash(user[2], password):
                # If user is admin or developer, allow admin access
                if user[4] in ['admin', 'developer']:
                    session['user_id'] = user[0]
                    session['user_email'] = user[1]
                    session['user_name'] = user[3]
                    session['is_admin'] = True
                    
                    # If they're also a developer, set that flag too
                    if user[4] == 'developer':
                        session['is_developer'] = True
                        
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash('Your account does not have admin privileges', 'error')
            else:
                flash('Invalid email or password', 'error')
                
    # For GET request, render the login template
    return render_template('login.html')

@app.route('/login')
def login():
    """Redirect to admin login for backward compatibility."""
    return redirect(url_for('admin_login'))

@app.route('/developer/login', methods=['GET', 'POST'])
def developer_login():
    """Login page for developer access."""
    if request.method == 'POST':
        # Check if it's a JSON request (Firebase auth)
        if request.is_json:
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
                    name = email.split('@')[0]
                
                # Only allow specific developer emails with Firebase
                if email != 'mr.haider.sm.ali@gmail.com' and not email.endswith('@dev.ocrcstutor.com'):
                    return jsonify({'error': 'This account does not have developer privileges'}), 403
                
                # Get or create developer user
                user = get_or_create_firebase_user(uid, email, name, 'developer')
                
                # Set session data
                session['user_id'] = user[0]
                session['user_email'] = user[1]
                session['user_name'] = user[3]
                session['is_developer'] = True
                session['is_admin'] = True  # Developer also has admin privileges
                session['firebase_token'] = id_token
                session['firebase_uid'] = uid
                
                return jsonify({
                    'success': True, 
                    'redirect': url_for('developer_dashboard')
                })
            except Exception as e:
                print(f"Error in developer_login: {e}")
                return jsonify({'error': str(e)}), 500
        else:
            # Traditional form-based login
            email = request.form.get('email')
            password = request.form.get('password')
            
            if not email or not password:
                flash('Email and password are required', 'error')
                return render_template('login.html', role='developer')
            
            # Only allow the specific developer email
            if email == 'mr.haider.sm.ali@gmail.com':
                # Check if user exists
                user = get_user_by_email(email)
                
                if user:
                    # For existing user, either check password or reset if it's the default
                    if password == 'password' or check_password_hash(user[2], password):
                        # Login successful
                        session['user_id'] = user[0]
                        session['user_email'] = user[1]
                        session['user_name'] = user[3]
                        session['is_developer'] = True
                        session['is_admin'] = True  # Developer also has admin privileges
                        
                        # If using default password, make sure hash is updated
                        if password == 'password' and not check_password_hash(user[2], password):
                            # Update password hash and role
                            conn = sqlite3.connect('user_database.db')
                            cursor = conn.cursor()
                            password_hash = generate_password_hash(password)
                            cursor.execute("UPDATE users SET password_hash = ?, role = 'developer' WHERE id = ?", 
                                          (password_hash, user[0]))
                            conn.commit()
                            conn.close()
                        else:
                            # Just update role to developer
                            conn = sqlite3.connect('user_database.db')
                            cursor = conn.cursor()
                            cursor.execute("UPDATE users SET role = 'developer' WHERE id = ?", (user[0],))
                            conn.commit()
                            conn.close()
                        
                        flash('Developer login successful', 'success')
                        return redirect(url_for('developer_dashboard'))
                    else:
                        flash('Invalid password', 'error')
                        return render_template('login.html', role='developer')
                else:
                    # Create new developer account with default password
                    success, user_id = create_user(email, password, 'Developer', 'developer')
                    if success:
                        session['user_id'] = user_id
                        session['user_email'] = email
                        session['user_name'] = 'Developer'
                        session['is_developer'] = True
                        session['is_admin'] = True  # Developer also has admin privileges
                        flash('Developer account created successfully', 'success')
                        return redirect(url_for('developer_dashboard'))
            else:
                flash('Invalid developer credentials', 'error')
                
    # For GET request, render the login template
    return render_template('login.html', role='developer')

@app.route('/logout')
def logout():
    """Logout user."""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    """API endpoint to refresh a Firebase token in the session."""
    try:
        data = request.json
        id_token = data.get('idToken')
        
        if not id_token:
            return jsonify({'error': 'No ID token provided'}), 400
            
        # Verify token
        success, uid, decoded_token = verify_firebase_token(id_token)
        if not success:
            return jsonify({'error': 'Invalid ID token'}), 401
            
        # Update token in session
        session['firebase_token'] = id_token
        
        # Check if the user is still valid and has the appropriate role
        if session.get('user_id'):
            user_id = session.get('user_id')
            
            # Get user data
            conn = sqlite3.connect('user_database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ? AND firebase_uid = ?", (user_id, uid))
            user = cursor.fetchone()
            conn.close()
            
            if not user:
                # User no longer exists or firebase_uid mismatch
                return jsonify({'error': 'User validation failed'}), 401
                
            # Update user role flags
            if user[4] == 'admin':
                session['is_admin'] = True
            else:
                session['is_admin'] = False
                
            if user[4] == 'developer':
                session['is_developer'] = True
                session['is_admin'] = True  # Developers are also admins
            else:
                session['is_developer'] = False
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return jsonify({'error': str(e)}), 500

# Admin routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard."""
    return render_template('admin/dashboard.html')

@app.route('/admin/topics')
@admin_required
def admin_topics():
    """View all available AI teaching topics."""
    # Get all topics from the curriculum
    topics = []
    for component, comp_data in OCR_CS_CURRICULUM.items():
        comp_title = comp_data['title']
        for topic in comp_data['topics']:
            # Extract topic code (e.g., "1.2" from "1.2 Software and software development")
            topic_parts = topic.split(' ', 1)
            if len(topic_parts) == 2:
                topic_code = topic_parts[0]
                topics.append({
                    'code': topic_code,
                    'title': topic,
                    'component': comp_title
                })
                
                # Get subtopics
                if topic_code in OCR_CS_DETAILED_TOPICS:
                    for subtopic in OCR_CS_DETAILED_TOPICS[topic_code]['subtopics']:
                        subtopic_parts = subtopic.split(' ', 1)
                        if len(subtopic_parts) == 2:
                            subtopic_code = subtopic_parts[0]
                            topics.append({
                                'code': subtopic_code,
                                'title': subtopic,
                                'component': comp_title,
                                'parent': topic
                            })
    
    # Sort topics by code
    topics.sort(key=lambda x: x['code'])
    
    return render_template('admin/topics.html', topics=topics)

# Developer routes
@app.route('/developer/dashboard')
@developer_required
def developer_dashboard():
    """Developer dashboard with access to all features."""
    return render_template('admin/developer_dashboard.html')

@app.route('/admin/resources')
@admin_required
def admin_resources():
    """View all resources."""
    rm = get_resource_manager()
    files = rm.get_all_file_info()
    return render_template('admin/resources.html', files=files)

@app.route('/admin/maintenance/cleanup-temp-files')
@admin_required
def admin_cleanup_temp_files():
    """Admin route to manually clean up temporary LaTeX files."""
    # Run the cleanup function
    cleanup_temp_latex_files()
    flash('Temporary LaTeX files cleanup completed', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload', methods=['GET', 'POST'])
@developer_required
def admin_upload():
    """Upload resources (developer only)."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            flash('No selected files', 'error')
            return redirect(request.url)
        
        category = request.form.get('category')
        
        # Process each file
        rm = get_resource_manager()
        processed_count = 0
        duplicate_count = 0
        error_count = 0
        
        for file in files:
            if file.filename == '':
                continue
                
            try:
                # Create a safe filename to avoid path issues
                safe_filename = os.path.basename(file.filename)
                print(f"Processing file: {safe_filename}")
                
                # Create temp directory if it doesn't exist
                temp_dir = os.path.join(os.getcwd(), 'temp_uploads')
                os.makedirs(temp_dir, exist_ok=True)
                
                # Save file temporarily with a unique name to avoid conflicts
                temp_path = os.path.join(temp_dir, f"{int(time.time())}_{safe_filename}")
                file.save(temp_path)
                print(f"File saved to: {temp_path}")
                
                # Process file
                file_id = rm.add_file(temp_path, category)
                print(f"File ID: {file_id}")
                
                if file_id:
                    rm.process_file_content(file_id)
                    processed_count += 1
                else:
                    duplicate_count += 1
                
                # Remove temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                print(f"Error processing file {file.filename}: {str(e)}")
                error_count += 1
        
        # Flash appropriate message based on results
        if processed_count > 0:
            flash(f'{processed_count} file(s) processed successfully', 'success')
        if duplicate_count > 0:
            flash(f'{duplicate_count} duplicate file(s) skipped', 'warning')
        if error_count > 0:
            flash(f'{error_count} file(s) could not be processed due to errors', 'error')
            
        return redirect(url_for('admin_resources'))
            
    return render_template('admin/upload.html')

# Student routes
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    """Student dashboard with topic selection."""
    return render_template('student/dashboard.html', 
                          curriculum=OCR_CS_CURRICULUM,
                          detailed_topics=OCR_CS_DETAILED_TOPICS,
                          user_name=session.get('user_name'))

@app.route('/student/topic/<component>/<topic_code>')
@login_required
def student_topic(component, topic_code):
    """Topic learning page."""
    # Use the topic lookup dictionary to get the title
    topic_info = OCR_CS_TOPIC_LOOKUP.get(topic_code)
    
    if topic_info:
        # We have info in our lookup dictionary
        topic_title = topic_info['full_title']
    else:
        # If not in our lookup, fallback to searching in curriculum
        topic_title = None
        
        # First check if it's in the main OCR curriculum
        if component in OCR_CS_CURRICULUM:
            for topic in OCR_CS_CURRICULUM[component]['topics']:
                if topic.startswith(topic_code):
                    topic_title = topic
                    break
    
        # If it's a detailed topic, get the title from detailed topics
        if not topic_title and topic_code in OCR_CS_DETAILED_TOPICS:
            topic_title = f"{topic_code} {OCR_CS_DETAILED_TOPICS[topic_code]['title']}"
        
        # If we still don't have a title, just use the topic code itself
        if not topic_title:
            topic_title = f"Topic {topic_code}"
    
    # Instead of clearing existing session data, we'll keep it
    # and let the JavaScript client handle session persistence
    
    return render_template('student/topic.html', 
                          component=component, 
                          topic_code=topic_code,
                          topic_title=topic_title,
                          learning_modes=LEARNING_MODES,
                          user_name=session.get('user_name'))

@app.route('/student/initial-prompt', methods=['POST'])
@login_required
def student_initial_prompt():
    """API endpoint for getting initial prompt based on topic and mode."""
    # Global dict to store pending requests
    if not hasattr(app, 'pending_initial_prompt_requests'):
        app.pending_initial_prompt_requests = {}
    
    try:
        data = request.json
        topic_code = data.get('topic_code')
        mode = data.get('mode', 'explore')
        stream_mode = data.get('stream', False)
        request_id = data.get('request_id')
        user_id = session.get('user_id')
        
        # Use our lookup dictionary to get topic information
        topic_info = OCR_CS_TOPIC_LOOKUP.get(topic_code)
        
        if topic_info:
            # We have info in our lookup dictionary
            if 'parent_code' in topic_info:
                # This is a subtopic
                parent_code = topic_info['parent_code']
                parent_info = OCR_CS_TOPIC_LOOKUP.get(parent_code)
                
                component = topic_info['component']
                main_topic = parent_info['full_title'] if parent_info else f"Topic {parent_code}"
                detailed_topic = topic_info['full_title']
            else:
                # This is a main topic
                component = topic_info['component']
                main_topic = topic_info['full_title']
                detailed_topic = main_topic
        else:
            # Fallback to the old method if not in lookup
            component = None
            main_topic = None
            detailed_topic = None
            
            # Search for the topic in the curriculum
            for comp, info in OCR_CS_CURRICULUM.items():
                for topic in info['topics']:
                    if topic.startswith(topic_code):
                        component = comp
                        main_topic = topic
                        detailed_topic = topic
                        break
                if component:
                    break
            
            # If it's a detailed topic, get it from detailed topics
            if not component and topic_code in OCR_CS_DETAILED_TOPICS:
                # Find the parent topic
                parent_code = '.'.join(topic_code.split('.')[:2])
                for comp, info in OCR_CS_CURRICULUM.items():
                    for topic in info['topics']:
                        if topic.startswith(parent_code):
                            component = comp
                            main_topic = topic
                            detailed_topic = topic_code + ' ' + OCR_CS_DETAILED_TOPICS[topic_code]['title']
                            break
                    if component:
                        break
            
            # If we still can't find the topic, create default values to prevent errors
            if not component:
                # Default to computer_systems if we can't determine the component
                component = 'computer_systems'
            
            if not main_topic:
                # Check if it's a subtopic by counting dots
                dots = topic_code.count('.')
                if dots >= 2:  # It's likely a subtopic (e.g., 1.1.1)
                    # Extract parent topic code (e.g., 1.1)
                    parent_code = '.'.join(topic_code.split('.')[:2])
                    main_topic = f"Topic {parent_code}"
                    
                    # If we have a title in detailed topics, use it
                    if topic_code in OCR_CS_DETAILED_TOPICS:
                        detailed_topic = topic_code + ' ' + OCR_CS_DETAILED_TOPICS[topic_code]['title']
                    else:
                        detailed_topic = f"Topic {topic_code}"
                else:
                    # It's a main topic
                    main_topic = f"Topic {topic_code}"
                    detailed_topic = main_topic
        
        # Create initial prompt
        initial_prompt = create_initial_prompt(component, main_topic, detailed_topic, mode)
        
        # Check if ANTHROPIC_API_KEY is set
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY is not set. Please set it in the environment variables.'}), 500
        
        # Start a new session in the database
        database = get_db()
        try:
            # Try to use the version with user_id
            session_id = database.start_session([component, main_topic, detailed_topic], user_id=user_id)
        except TypeError:
            # Fall back to original function if user_id parameter doesn't exist
            session_id = database.start_session([component, main_topic, detailed_topic])
            
            # Add monkey patching for basic OCRCSDatabase class to support user verification
            if not hasattr(database, 'verify_session_ownership'):
                def verify_session_ownership(self, session_id, user_id):
                    """Check if a session belongs to a user - basic implementation always returns True."""
                    return True
                database.verify_session_ownership = verify_session_ownership.__get__(database)
        
        # Store session ID in Flask session
        session['db_session_id'] = session_id
        session['current_topic'] = main_topic
        session['current_detailed_topic'] = detailed_topic
        
        # Add user message to database
        database.add_message(session_id, "user", initial_prompt)
        
        # If streaming is requested, use the same pattern as student_chat
        if stream_mode and request_id:
            # Store the request data for the streaming endpoint to pick up
            request_key = f"{user_id}:{request_id}"
            app.pending_initial_prompt_requests[request_key] = {
                'question': initial_prompt,
                'conversation_history': [{"role": "user", "content": initial_prompt}],
                'topic_code': topic_code,
                'mode': mode,
                'session_id': session_id,
                'timestamp': time.time()
            }
            
            # Return successful acknowledgement - client will connect to SSE endpoint
            return jsonify({'success': True, 'streaming': True, 'session_id': session_id})
        else:
            # Non-streaming response (original functionality)
            response = get_claude_response(initial_prompt, topic_code=topic_code, mode=mode)
            
            # Add assistant message to database
            database.add_message(session_id, "assistant", response)
            
            return jsonify({'response': response})
    except Exception as e:
        print(f"Error in student_initial_prompt: {str(e)}")
        return jsonify({'error': f'Error generating initial response: {str(e)}'}), 500

# Function to generate streaming response for student chat
def generate_student_chat_stream(question, conversation_history, topic_code=None, mode="explore"):
    """Generate streaming response for topic-specific student chat."""
    client = get_anthropic_client()
    
    try:
        # Get streaming response
        response_stream = get_claude_response(question, conversation_history, topic_code, stream=True, mode=mode)
        
        # Track full response for conversation history
        full_response = ""
        
        # Stream each chunk as it comes
        for chunk in response_stream:
            # Handle different response formats from Anthropic API
            if hasattr(chunk, 'type') and chunk.type == "content_block_delta":
                # New API format
                text = chunk.delta.text
                if text:  # Only send non-empty text
                    full_response += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
            elif isinstance(chunk, dict) and 'completion' in chunk:
                # Old API format (for backward compatibility)
                text = chunk.get('completion', '')
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
            elif isinstance(chunk, str):
                # Simple string response (fallback)
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        # Send the final response with the complete content
        yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
    except Exception as e:
        # Log the error for debugging
        print(f"Error in streaming response: {str(e)}")
        # Send an error message to the client
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@app.route('/student/chat', methods=['POST', 'GET'])
@login_required
def student_chat():
    """API endpoint for chat interactions for the logged-in user."""
    # Global dict to store pending requests
    if not hasattr(app, 'pending_student_chat_requests'):
        app.pending_student_chat_requests = {}
    
    # Handle GET request for EventSource
    if request.method == 'GET':
        request_id = request.args.get('request_id')
        
        if request_id:
            user_id = session.get('user_id')
            request_key = f"{user_id}:{request_id}"
            
            # Check if this is a valid pending request in student chat
            if request_key in app.pending_student_chat_requests:
                request_data = app.pending_student_chat_requests[request_key]
                
                # Return SSE stream with the pending question data
                return Response(
                    generate_student_chat_stream(
                        request_data['question'], 
                        request_data['conversation_history'],
                        request_data['topic_code'],
                        request_data.get('mode', 'explore')
                    ),
                    mimetype='text/event-stream'
                )
            
            # Check if this is a valid pending request for initial prompt
            elif hasattr(app, 'pending_initial_prompt_requests') and request_key in app.pending_initial_prompt_requests:
                request_data = app.pending_initial_prompt_requests[request_key]
                
                # Return SSE stream with the pending initial prompt data
                return Response(
                    generate_student_chat_stream(
                        request_data['question'], 
                        request_data['conversation_history'],
                        request_data['topic_code'],
                        request_data.get('mode', 'explore')
                    ),
                    mimetype='text/event-stream'
                )
        
        # For simple connection test or invalid IDs
        def keep_alive():
            yield f"data: {json.dumps({'connected': True})}\n\n"
        return Response(keep_alive(), mimetype='text/event-stream')
        
    try:
        data = request.json
        question = data.get('question')
        topic_code = data.get('topic_code')
        mode = data.get('mode', 'explore')
        stream_mode = data.get('stream', False)
        user_id = session.get('user_id')
        
        # Get session ID from Flask session
        session_id = session.get('db_session_id')
        
        # Get conversation history from database
        database = get_db()
        conversation_history = []
        if session_id:
            # Verify this session belongs to the current user
            if database.verify_session_ownership(session_id, user_id):
                messages = database.get_session_messages(session_id)
                for _, role, content in messages:
                    conversation_history.append({"role": role, "content": content})
            else:
                return jsonify({'error': 'Session not found or unauthorized'}), 403
        
        # Check if ANTHROPIC_API_KEY is set
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY is not set. Please set it in the environment variables.'}), 500
        
        # If streaming is requested, use Server-Sent Events
        if stream_mode:
            # Add user message to database
            if session_id:
                database.add_message(session_id, "user", question)
            
            # Get request ID from client
            request_id = data.get('request_id')
            
            if request_id:
                # Store the request data for the streaming endpoint to pick up
                request_key = f"{user_id}:{request_id}"
                app.pending_student_chat_requests[request_key] = {
                    'question': question,
                    'conversation_history': conversation_history,
                    'topic_code': topic_code,
                    'mode': mode,
                    'session_id': session_id,
                    'timestamp': time.time()
                }
                
                # Return successful acknowledgement - client will connect to SSE endpoint
                return jsonify({'success': True, 'streaming': True})
            else:
                # For backward compatibility - use direct streaming if no request_id provided
                # Store session_id in local variable for the closure
                current_session_id = session_id
                
                # Function to generate SSE data
                def generate():
                    try:
                        nonlocal current_session_id
                        # Get streaming response
                        response_stream = get_claude_response(question, conversation_history, topic_code, stream=True, mode=mode)
                        
                        # Track full response for database
                        full_response = ""
                        
                        # Stream each chunk as it comes
                        for chunk in response_stream:
                            # Handle different response formats from Anthropic API
                            if hasattr(chunk, 'type') and chunk.type == "content_block_delta":
                                # New API format
                                text = chunk.delta.text
                                if text:  # Only send non-empty text
                                    full_response += text
                                    yield f"data: {json.dumps({'text': text})}\n\n"
                            elif isinstance(chunk, dict) and 'completion' in chunk:
                                # Old API format (for backward compatibility)
                                text = chunk.get('completion', '')
                                if text:
                                    full_response += text
                                    yield f"data: {json.dumps({'text': text})}\n\n"
                            elif isinstance(chunk, str):
                                # Simple string response (fallback)
                                full_response += chunk
                                yield f"data: {json.dumps({'text': chunk})}\n\n"
                        
                        # Signal the end of the stream with the full response
                        yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
                    except Exception as e:
                        print(f"Error in direct streaming: {str(e)}")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                
                return Response(generate(), mimetype='text/event-stream')
        else:
            # Non-streaming response (original functionality)
            response = get_claude_response(question, conversation_history, topic_code, mode=mode)
            
            # Add messages to database
            if session_id:
                database.add_message(session_id, "user", question)
                database.add_message(session_id, "assistant", response)
            
            return jsonify({'response': response})
            
    except Exception as e:
        print(f"Error in student_chat: {str(e)}")
        return jsonify({'error': f'Error generating response: {str(e)}'}), 500

@app.route('/student/progress')
@login_required
def student_progress():
    """View student progress for the logged-in user."""
    user_id = session.get('user_id')
    database = get_db()
    
    try:
        # Try to filter by user_id
        topic_progress = database.get_topic_progress(user_id=user_id)
        exam_progress = database.get_exam_progress(user_id=user_id)
    except (sqlite3.OperationalError, TypeError) as e:
        # Fallback if we get "no such column" error or TypeError (when function doesn't accept user_id parameter)
        if isinstance(e, sqlite3.OperationalError) and "no such column: user_id" in str(e):
            print(f"Warning: User ID column missing - using unfiltered data: {e}")
        elif isinstance(e, TypeError):
            print(f"Warning: Database function doesn't accept user_id parameter: {e}")
        # Fallback to unfiltered data
        topic_progress = database.get_topic_progress()
        exam_progress = database.get_exam_progress()
    except Exception as e:
        # Re-raise if it's some other error
        print(f"Error in student_progress: {e}")
        raise
    
    return render_template('student/progress.html', 
                          topic_progress=topic_progress,
                          exam_progress=exam_progress,
                          user_name=session.get('user_name'))

@app.route('/student/rate-topic', methods=['POST'])
@login_required
def student_rate_topic():
    """Rate understanding of a topic for the logged-in user."""
    data = request.json
    user_id = session.get('user_id')
    topic_code = data.get('topic_code')
    topic_title = data.get('topic_title')
    rating = data.get('rating')
    notes = data.get('notes', '')
    
    if not topic_code or not topic_title or not rating:
        return jsonify({'error': 'Missing required fields'})
    
    database = get_db()
    try:
        # Try to update with user_id
        database.update_topic_progress(topic_code, topic_title, rating, notes, user_id=user_id)
    except sqlite3.OperationalError as e:
        # Fallback if we get "no such column" error
        if "no such column: user_id" in str(e):
            print(f"Warning: User ID column missing in topic_progress: {e}")
            # Fallback to non-user-specific update
            database.update_topic_progress(topic_code, topic_title, rating, notes)
        else:
            # Re-raise if it's some other database error
            raise
    
    return jsonify({'success': True})

@app.route('/student/record-exam', methods=['POST'])
@login_required
def student_record_exam():
    """Record exam practice results for the logged-in user."""
    data = request.json
    user_id = session.get('user_id')
    topic_code = data.get('topic_code')
    score = data.get('score')
    max_score = data.get('max_score')
    
    # Set default values for simplified interface
    question_type = data.get('question_type', 'exam')
    difficulty = data.get('difficulty', 2)  # Medium difficulty by default
    
    if not all([topic_code, score, max_score]):
        return jsonify({'error': 'Missing required fields: topic_code, score, and max_score are required'})
    
    database = get_db()
    try:
        # Try to record with user_id
        database.record_exam_practice(topic_code, question_type, difficulty, score, max_score, user_id=user_id)
    except Exception as e:
        # Check if it's the user_id parameter error
        if isinstance(e, TypeError) and "got an unexpected keyword argument 'user_id'" in str(e):
            # Fallback to non-user-specific record
            database.record_exam_practice(topic_code, question_type, difficulty, score, max_score)
        elif isinstance(e, sqlite3.OperationalError) and "no such column: user_id" in str(e):
            # Fallback if we get "no such column" error
            database.record_exam_practice(topic_code, question_type, difficulty, score, max_score)
        else:
            # Re-raise if it's some other error
            raise
    
    return jsonify({'success': True})

@app.route('/student/save-response', methods=['POST'])
@login_required
def save_response():
    """Save complete Claude response to the database after streaming."""
    data = request.json
    session_id = data.get('session_id')
    response = data.get('response')
    user_id = session.get('user_id')
    
    if not session_id or not response:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Get database
    database = get_db()
    
    # Verify this session belongs to the current user
    if database.verify_session_ownership(session_id, user_id):
        # Save response to database
        database.add_message(session_id, "assistant", response)
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Session not found or unauthorized'}), 403

@app.route('/student/get-recent-messages', methods=['POST'])
@login_required
def get_recent_messages():
    """Get the last 10 messages for a given session."""
    data = request.json
    session_id = data.get('session_id')
    user_id = session.get('user_id')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id parameter'}), 400
    
    # Get database
    database = get_db()
    
    # Verify this session belongs to the current user
    if database.verify_session_ownership(session_id, user_id):
        # Get recent messages (limited to last 10)
        messages = database.get_session_messages(session_id)
        
        # If there are more than 10 messages, get only the last 10
        if len(messages) > 10:
            messages = messages[-10:]
        
        # Format messages for frontend
        formatted_messages = []
        for _, role, content in messages:
            formatted_messages.append({
                "role": role,
                "content": content
            })
        
        return jsonify({
            'success': True,
            'messages': formatted_messages
        })
    else:
        return jsonify({'error': 'Session not found or unauthorized'}), 403

@app.route('/student/clear-chat-history', methods=['POST'])
@login_required
def clear_chat_history():
    """Clear all messages for a given session and prepare to start fresh."""
    data = request.json
    session_id = data.get('session_id')
    user_id = session.get('user_id')
    
    if not session_id:
        return jsonify({'error': 'Missing session_id parameter'}), 400
    
    # Get database
    database = get_db()
    
    # Verify this session belongs to the current user
    if database.verify_session_ownership(session_id, user_id):
        try:
            # Delete all messages for this session
            conn = sqlite3.connect('ocr_cs_tutor.db')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_history WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Chat history cleared successfully'
            })
        except Exception as e:
            return jsonify({'error': f'Database error: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Session not found or unauthorized'}), 403

@app.route('/resources/<path:filename>')
def serve_resource(filename):
    """Serve resource files (PDFs, etc.)."""
    return send_from_directory('resources', filename)

@app.route('/generate-exam-pdf', methods=['POST'])
@login_required
def generate_exam_pdf():
    """Generate a PDF from LaTeX content."""
    data = request.json
    topic_title = data.get('topic_title', 'OCR Computer Science Practice Paper')
    content = data.get('content', '')
    topic_code = data.get('topic_code', '')
    user_id = session.get('user_id')
    
    if not content:
        return jsonify({'error': 'No content provided'}), 400
    
    # Check if content contains LaTeX markers
    contains_latex = '\\documentclass' in content or '\\begin{document}' in content
    
    # If it's not already a complete LaTeX document, wrap it
    if not contains_latex:
        content = generate_latex_document(topic_title, content)
    
    # Import the LaTeX compiler
    from latex_compiler import compile_latex_to_pdf
    
    # Compile LaTeX to PDF
    pdf_path = compile_latex_to_pdf(content, user_id, topic_code, topic_title)
    
    if not pdf_path:
        return jsonify({
            'error': 'PDF compilation failed', 
            'details': 'Check server logs for details'
        }), 500
    
    try:
        # Connect to database
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        
        # Store in database
        cursor.execute(
            "INSERT INTO generated_pdfs (user_id, topic_code, title, latex_content, pdf_path) VALUES (?, ?, ?, ?, ?)",
            (user_id, topic_code, topic_title, content, pdf_path)
        )
        
        pdf_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Legacy cleanup for backward compatibility
        cleanup_old_pdfs(user_id)
        
        # Return URL to the generated PDF
        pdf_url = url_for('static', filename=pdf_path, _external=True)
        
        return jsonify({
            'success': True,
            'pdf_url': pdf_url,
            'pdf_id': pdf_id
        })
    except Exception as e:
        return jsonify({
            'error': 'Error storing PDF information', 
            'details': str(e)
        }), 500

@app.route('/temp_latex/<filename>')
@login_required
def serve_pdf(filename):
    """Serve PDF files."""
    return send_from_directory('temp_latex', filename, mimetype='application/pdf')

@app.route('/student/pdf-library')
@login_required
def pdf_library():
    """Show all PDFs created by the user."""
    user_id = session.get('user_id')
    
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Get PDFs from generated_pdfs table (new system)
    cursor.execute(
        "SELECT id, topic_code, title, created_at, pdf_path FROM generated_pdfs WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    
    pdfs = cursor.fetchall()
    
    # Get PDFs from latex_pdfs table (old system) for backward compatibility
    cursor.execute(
        "SELECT id, topic_code, topic_title, created_at, filename FROM latex_pdfs WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    
    legacy_pdfs = cursor.fetchall()
    
    # Convert legacy PDFs to the same format as new PDFs
    for i, (pdf_id, topic_code, title, created_at, filename) in enumerate(legacy_pdfs):
        # Replace filename path with URL path format
        legacy_pdfs[i] = (pdf_id, topic_code, title, created_at, f"temp_latex/{filename.replace('.tex', '.pdf')}")
    
    # Combine both PDF lists
    all_pdfs = pdfs + legacy_pdfs
    
    conn.close()
    
    return render_template('student/pdf_library.html', 
                          pdfs=all_pdfs,
                          user_name=session.get('user_name'))

# Progress Tracking Widget Routes

@app.route('/student/track-activity', methods=['POST'])
@login_required
def track_activity():
    """Track user activity for streak calculation."""
    data = request.json
    user_id = session.get('user_id')
    activity_type = data.get('activity_type', 'page_view')
    session_duration = data.get('session_duration', 0)
    
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        # Get current date in YYYY-MM-DD format
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Connect to database
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        
        # Check if user already has activity for today
        cursor.execute(
            "SELECT id FROM user_activity WHERE user_id = ? AND activity_date = ?",
            (user_id, today)
        )
        
        existing_activity = cursor.fetchone()
        
        if existing_activity:
            # Update existing activity record
            cursor.execute(
                "UPDATE user_activity SET session_duration = session_duration + ? WHERE user_id = ? AND activity_date = ?",
                (session_duration, user_id, today)
            )
        else:
            # Create new activity record
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_date, activity_type, session_duration) VALUES (?, ?, ?, ?)",
                (user_id, today, activity_type, session_duration)
            )
        
        conn.commit()
        
        # Calculate current streak
        streak_data = calculate_user_streak(user_id)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'streak': streak_data['streak'],
            'streakAtRisk': streak_data['streak_at_risk']
        })
    except Exception as e:
        print(f"Error tracking activity: {str(e)}")
        return jsonify({'error': f'Error tracking activity: {str(e)}'}), 500

@app.route('/student/get-activity-data', methods=['GET'])
@login_required
def get_activity_data():
    """Get user activity data for calendar visualization."""
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        
        # Calculate first day of the month and last day of the month
        today = datetime.now()
        year = request.args.get('year', today.year, type=int)
        month = request.args.get('month', today.month, type=int)
        
        start_date = datetime(year, month, 1).strftime('%Y-%m-%d')
        # Get the last day of the month
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')
        
        # Get activity data for the specified month
        cursor.execute(
            """
            SELECT activity_date, activity_type, session_duration 
            FROM user_activity 
            WHERE user_id = ? AND activity_date BETWEEN ? AND ?
            ORDER BY activity_date
            """,
            (user_id, start_date, end_date)
        )
        
        activities = cursor.fetchall()
        
        # Calculate streak
        streak_data = calculate_user_streak(user_id)
        
        # Format activity data for the calendar
        activity_data = []
        for date, activity_type, duration in activities:
            # Determine activity level (1-4) based on duration or other metrics
            # This is a simple example - you may want to use more sophisticated logic
            level = 1  # Default level
            if duration > 3600:  # More than 1 hour
                level = 4
            elif duration > 1800:  # More than 30 minutes
                level = 3
            elif duration > 600:  # More than 10 minutes
                level = 2
                
            activity_data.append({
                'date': date,
                'type': activity_type,
                'level': level
            })
        
        conn.close()
        
        return jsonify({
            'activityData': activity_data,
            'currentStreak': streak_data['streak'],
            'streakAtRisk': streak_data['streak_at_risk']
        })
    except Exception as e:
        print(f"Error getting activity data: {str(e)}")
        return jsonify({'error': f'Error getting activity data: {str(e)}'}), 500

@app.route('/student/get-topic-progress', methods=['GET'])
@login_required
def get_topic_progress_data():
    """Get topic progress data for spaced repetition recommendations."""
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        # Get database instance
        database = get_db()
        
        # Get topic progress data
        try:
            # Try to get user-specific progress data
            progress_data = database.get_topic_progress(user_id=user_id)
        except (sqlite3.OperationalError, TypeError) as e:
            # Fallback to unfiltered data if filtering by user_id fails
            progress_data = database.get_topic_progress()
        
        # Format topic progress data for the frontend
        formatted_data = []
        for topic_code, topic_title, last_studied, proficiency, notes in progress_data:
            formatted_data.append({
                'topicCode': topic_code,
                'topicTitle': topic_title,
                'lastStudied': last_studied,
                'proficiency': proficiency,
                'notes': notes
            })
        
        return jsonify(formatted_data)
    except Exception as e:
        print(f"Error getting topic progress: {str(e)}")
        return jsonify({'error': f'Error getting topic progress: {str(e)}'}), 500

@app.route('/student/mark-topic-reviewed', methods=['POST'])
@login_required
def mark_topic_reviewed():
    """Mark a topic as reviewed today (updates last_studied date and tracks activity)."""
    data = request.json
    user_id = session.get('user_id')
    topic_code = data.get('topic_code')
    
    if not user_id or not topic_code:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        # Get database instance
        database = get_db()
        
        # Get existing topic data to preserve proficiency and notes
        try:
            # Try with user_id
            progress_data = database.get_topic_progress(user_id=user_id)
        except (sqlite3.OperationalError, TypeError):
            # Fallback
            progress_data = database.get_topic_progress()
        
        # Find the topic in progress data
        topic_data = None
        for data_topic_code, topic_title, _, proficiency, notes in progress_data:
            if data_topic_code == topic_code:
                topic_data = {
                    'topic_code': data_topic_code,
                    'topic_title': topic_title,
                    'proficiency': proficiency,
                    'notes': notes
                }
                break
        
        if not topic_data:
            return jsonify({'error': 'Topic not found in progress data'}), 404
        
        # Update the topic progress with today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get a direct database connection to verify the update
        conn = sqlite3.connect('ocr_cs_tutor.db')
        cursor = conn.cursor()
        
        # First check if there's a user_id column in the topic_progress table
        cursor.execute("PRAGMA table_info(topic_progress)")
        columns = [col[1] for col in cursor.fetchall()]
        has_user_id = 'user_id' in columns
        
        # Update directly with SQL to ensure it works
        if has_user_id:
            # If we have a user_id column, use it
            cursor.execute(
                """
                UPDATE topic_progress 
                SET last_studied = ? 
                WHERE topic_code = ? AND user_id = ?
                """, 
                (today, topic_code, user_id)
            )
        else:
            # Fallback to update without user_id
            cursor.execute(
                """
                UPDATE topic_progress 
                SET last_studied = ? 
                WHERE topic_code = ?
                """, 
                (today, topic_code)
            )
        
        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"Updated topic {topic_code} for user {user_id}, rows affected: {rows_updated}")
        
        # Also try the ORM update as a backup
        try:
            # Try to update with user_id
            database.update_topic_progress(
                topic_data['topic_code'],
                topic_data['topic_title'],
                topic_data['proficiency'],
                topic_data['notes'],
                user_id=user_id,
                last_studied=today
            )
        except (sqlite3.OperationalError, TypeError) as e:
            # Fallback if user_id parameter fails
            if "user_id" in str(e):
                database.update_topic_progress(
                    topic_data['topic_code'],
                    topic_data['topic_title'],
                    topic_data['proficiency'],
                    topic_data['notes'],
                    last_studied=today
                )
            else:
                # Log but don't re-raise since we already tried direct SQL update
                print(f"ORM update failed but SQL update may have succeeded: {e}")
        
        # Also record this as an activity for streak tracking
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        
        # Check if user already has activity for today
        cursor.execute(
            "SELECT id FROM user_activity WHERE user_id = ? AND activity_date = ?",
            (user_id, today)
        )
        
        existing_activity = cursor.fetchone()
        
        if existing_activity:
            # Update existing activity record
            cursor.execute(
                "UPDATE user_activity SET session_duration = session_duration + 600 WHERE user_id = ? AND activity_date = ?",
                (user_id, today)
            )
        else:
            # Create new activity record
            cursor.execute(
                "INSERT INTO user_activity (user_id, activity_date, activity_type, session_duration) VALUES (?, ?, ?, ?)",
                (user_id, today, "topic_review", 600)  # 10 minutes by default
            )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error marking topic as reviewed: {str(e)}")
        return jsonify({'error': f'Error marking topic as reviewed: {str(e)}'}), 500

# Helper function for streak calculation
def calculate_user_streak(user_id):
    """Calculate a user's current streak and whether it's at risk."""
    conn = sqlite3.connect('user_database.db')
    cursor = conn.cursor()
    
    # Get today's date and yesterday's date
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)
    
    # Format dates as strings
    today_str = today.strftime('%Y-%m-%d')
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    two_days_ago_str = two_days_ago.strftime('%Y-%m-%d')
    
    # Check if user has activity for today
    cursor.execute(
        "SELECT 1 FROM user_activity WHERE user_id = ? AND activity_date = ?",
        (user_id, today_str)
    )
    has_activity_today = cursor.fetchone() is not None
    
    # Check if user has activity for yesterday
    cursor.execute(
        "SELECT 1 FROM user_activity WHERE user_id = ? AND activity_date = ?",
        (user_id, yesterday_str)
    )
    has_activity_yesterday = cursor.fetchone() is not None
    
    # Check if user has activity for two days ago
    cursor.execute(
        "SELECT 1 FROM user_activity WHERE user_id = ? AND activity_date = ?",
        (user_id, two_days_ago_str)
    )
    has_activity_two_days_ago = cursor.fetchone() is not None
    
    # Get all activity dates for this user in descending order
    cursor.execute(
        "SELECT activity_date FROM user_activity WHERE user_id = ? ORDER BY activity_date DESC",
        (user_id,)
    )
    activity_dates = [datetime.strptime(row[0], '%Y-%m-%d').date() for row in cursor.fetchall()]
    
    conn.close()
    
    # If no activity, streak is 0
    if not activity_dates:
        return {'streak': 0, 'streak_at_risk': False}
    
    # Calculate streak
    streak = 0
    streak_at_risk = False
    
    # If user has activity today, start counting from today
    if has_activity_today:
        streak = 1
        date_to_check = yesterday
    # If user has activity yesterday but not today, start counting from yesterday
    # and mark streak as at risk
    elif has_activity_yesterday:
        streak = 1
        date_to_check = two_days_ago
        streak_at_risk = True
    # If user has activity two days ago but not yesterday or today,
    # streak is 0 (streak was broken)
    else:
        return {'streak': 0, 'streak_at_risk': False}
    
    # Continue counting streak from previous days
    for date in activity_dates:
        if date == today or date == yesterday:
            # Skip today and yesterday as they were already counted
            continue
            
        if date == date_to_check:
            streak += 1
            date_to_check = date_to_check - timedelta(days=1)
        else:
            # Allow for one missed day in the streak
            if date == date_to_check - timedelta(days=1) and not streak_at_risk:
                streak_at_risk = True
                date_to_check = date - timedelta(days=1)
            else:
                # Streak is broken
                break
    
    return {'streak': streak, 'streak_at_risk': streak_at_risk}

@app.route('/get-profile-picture', methods=['GET'])
@login_required
def get_profile_picture():
    """Get the profile picture URL for the logged-in user."""
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    try:
        # Get user data
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT profile_picture_url FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            # Return profile picture URL if found
            return jsonify({
                'success': True,
                'profile_picture_url': result[0]
            })
        else:
            # No profile picture found
            return jsonify({
                'success': False,
                'message': 'No profile picture found'
            })
    except Exception as e:
        print(f"Error getting profile picture: {str(e)}")
        return jsonify({'error': f'Error getting profile picture: {str(e)}'}), 500

@app.route('/student/delete-pdf', methods=['POST'])
@login_required
def delete_pdf():
    """Delete a PDF created by the user."""
    data = request.json
    pdf_id = data.get('pdf_id')
    user_id = session.get('user_id')
    
    if not pdf_id:
        return jsonify({'error': 'Missing PDF ID'}), 400
    
    try:
        conn = sqlite3.connect('user_database.db')
        cursor = conn.cursor()
        
        # First check if it's in the generated_pdfs table
        cursor.execute(
            "SELECT pdf_path FROM generated_pdfs WHERE id = ? AND user_id = ?", 
            (pdf_id, user_id)
        )
        
        result = cursor.fetchone()
        
        if result:
            # It's in the new system
            pdf_path = result[0]
            
            # Delete the physical file
            file_path = os.path.join('static', pdf_path)
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Delete the database record
            cursor.execute(
                "DELETE FROM generated_pdfs WHERE id = ? AND user_id = ?", 
                (pdf_id, user_id)
            )
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True})
        else:
            # Check if it's in the legacy system
            cursor.execute(
                "SELECT filename FROM latex_pdfs WHERE id = ? AND user_id = ?", 
                (pdf_id, user_id)
            )
            
            result = cursor.fetchone()
            
            if result:
                # It's in the old system
                filename = result[0]
                
                # Delete the physical files (both .tex and .pdf)
                tex_path = os.path.join('temp_latex', filename)
                pdf_path = tex_path.replace('.tex', '.pdf')
                
                if os.path.exists(tex_path):
                    os.remove(tex_path)
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                
                # Delete the database record
                cursor.execute(
                    "DELETE FROM latex_pdfs WHERE id = ? AND user_id = ?", 
                    (pdf_id, user_id)
                )
                
                conn.commit()
                conn.close()
                
                return jsonify({'success': True})
            
            # If we get here, the PDF wasn't found
            conn.close()
            return jsonify({'error': 'PDF not found or unauthorized'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Error deleting PDF: {str(e)}'}), 500

# Function to generate streaming response for global chat
def generate_global_chat_stream(question, conversation_history):
    """Generate streaming response for global chat."""
    # Create a system prompt specifically for general CS questions
    general_system_prompt = """
    You are an expert OCR A-Level Computer Science tutor. Answer any computer science questions concisely and accurately.
    Focus on OCR A-Level curriculum topics, but be prepared to answer general computer science questions too.
    Keep responses brief (200-300 words) and use bullet points where appropriate.
    Include code examples only when necessary and keep them short.
    End with 1-2 key takeaways.
    """
    
    client = get_anthropic_client()
    
    try:
        # Create a message and get the streaming response
        response_stream = client.messages.create(
            model=AI_MODEL,
            max_tokens=1024,
            temperature=0.7,
            system=general_system_prompt,
            messages=conversation_history,
            stream=True
        )
        
        # Track full response for conversation history
        full_response = ""
        
        # Stream each chunk as it comes
        for chunk in response_stream:
            # Handle different response formats from Anthropic API
            if hasattr(chunk, 'type') and chunk.type == "content_block_delta":
                # New API format
                text = chunk.delta.text
                if text:  # Only send non-empty text
                    full_response += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
            elif isinstance(chunk, dict) and 'completion' in chunk:
                # Old API format (for backward compatibility)
                text = chunk.get('completion', '')
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
            elif isinstance(chunk, str):
                # Simple string response (fallback)
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        
        # Send the final response with the complete content
        yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
    except Exception as e:
        # Log the error for debugging
        print(f"Error in global chat streaming response: {str(e)}")
        # Send an error message to the client
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@app.route('/global-chat', methods=['POST', 'GET'])
@login_required
def global_chat():
    """API endpoint for general CS questions (not tied to a specific topic) for the logged-in user."""
    # Global dict to store pending requests
    if not hasattr(app, 'pending_global_chat_requests'):
        app.pending_global_chat_requests = {}
    
    # Handle GET request for EventSource
    if request.method == 'GET':
        request_id = request.args.get('request_id')
        
        if request_id:
            user_id = session.get('user_id')
            request_key = f"{user_id}:{request_id}"
            
            # Check if this is a valid pending request
            if request_key in app.pending_global_chat_requests:
                request_data = app.pending_global_chat_requests[request_key]
                
                # Return SSE stream with the pending question data
                return Response(
                    generate_global_chat_stream(
                        request_data['question'], 
                        request_data['conversation_history']
                    ),
                    mimetype='text/event-stream'
                )
        
        # For simple connection test or invalid IDs
        def keep_alive():
            yield f"data: {json.dumps({'connected': True})}\n\n"
        return Response(keep_alive(), mimetype='text/event-stream')
    
    # Handle POST request
    try:
        data = request.json
        question = data.get('question')
        user_id = session.get('user_id')
        stream_mode = data.get('stream', False)
        request_id = data.get('request_id')
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        # Create a session-specific key for global chat
        global_chat_key = f'global_chat_history_{user_id}'
            
        # Create a session key for global chat if it doesn't exist
        if global_chat_key not in session:
            session[global_chat_key] = []
            
        # Get conversation history from session
        conversation_history = session.get(global_chat_key, [])
        
        # Check if ANTHROPIC_API_KEY is set
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY is not set. Please set it in the environment variables.'}), 500
        
        # Create a system prompt specifically for general CS questions
        general_system_prompt ="""
You are an expert OCR A-Level Computer Science tutor. Your role is to answer any computer science questions concisely and accurately, focusing on the OCR A-Level curriculum but also addressing general computer science queries if needed.

**Response Guidelines**:
- Keep responses brief (100–300 words) and, where possible, use bullet points.
- Include short code examples only when absolutely necessary.
- End every response with 1–2 key takeaways that help reinforce understanding.
- Integrate Pólya’s “How to Solve It” principles in your explanations:
  - **Understanding the Problem**: Ensure the student fully grasps the question or scenario.
  - **Devising a Plan**: Encourage brainstorming and propose strategies or potential methods.
  - **Carrying Out the Plan**: Demonstrate clear reasoning and, if relevant, short code snippets.
  - **Looking Back**: Prompt reflection on the solution, emphasizing possible improvements or generalizations.

Keep your tone supportive and succinct. When a student asks for deeper insights, respond with short, targeted guidance—ask clarifying questions to draw out their reasoning rather than simply providing the answer. Encourage them to make connections with other OCR curriculum areas or prior knowledge, helping them cultivate strong problem-solving skills and a holistic view of computer science.
"""        
        # Get response from Claude
        client = get_anthropic_client()
        
        # Prepare messages
        messages = []
        for msg in conversation_history:
            messages.append(msg)
            
        # Add the current question
        messages.append({"role": "user", "content": question})
        
        # Update conversation history with user message
        conversation_history.append({"role": "user", "content": question})
        session[global_chat_key] = conversation_history
        
        # If streaming is requested, use Server-Sent Events
        if stream_mode and request_id:
            # Store the request data for the streaming endpoint to pick up
            request_key = f"{user_id}:{request_id}"
            app.pending_global_chat_requests[request_key] = {
                'question': question,
                'conversation_history': messages,
                'timestamp': time.time()
            }
            
            # Return successful acknowledgement - client will connect to SSE endpoint
            return jsonify({'success': True, 'streaming': True})
        elif stream_mode:
            # Function to generate SSE data directly
            def generate():
                # Create a message and get the streaming response
                response_stream = client.messages.create(
                    model=AI_MODEL,
                    max_tokens=1024,
                    temperature=0.7,
                    system=general_system_prompt,
                    messages=messages,
                    stream=True
                )
                
                # Track full response for conversation history
                full_response = ""
                
                # Stream each chunk as it comes
                for chunk in response_stream:
                    if chunk.type == "content_block_delta":
                        text = chunk.delta.text
                        if text:  # Only send non-empty text
                            full_response += text
                            yield f"data: {json.dumps({'text': text})}\n\n"
                
                # Send the final response with the complete content
                yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            # Non-streaming response (original functionality)
            # Create a message and get the response
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=1024,
                temperature=0.7,
                system=general_system_prompt,
                messages=messages
            )
            
            # Get the response text
            response_text = response.content[0].text
            
            # Update conversation history with the response
            conversation_history.append({"role": "assistant", "content": response_text})
            
            # Keep only the last 10 messages
            if len(conversation_history) > 10:
                conversation_history = conversation_history[-10:]
                
            # Update session
            session[global_chat_key] = conversation_history
            
            return jsonify({'response': response_text})
            
    except Exception as e:
        print(f"Error in global_chat: {str(e)}")
        return jsonify({'error': f'Error generating response: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
