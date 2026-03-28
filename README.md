StudyQuest CLI — AI-Powered Gamified Study Planner
StudyQuest CLI is a command-line application designed to help users track, analyze, and improve their study habits. It combines productivity tracking with gamification elements such as levels, streaks, and badges, along with intelligent recommendations powered by Machine Learning and Reinforcement Learning.
________________________________________
Overview
The application allows user to:
•	Log study sessions with contextual data (duration, focus, sleep, distractions)
•	Track goals and monitor progress
•	Receive AI-generated daily study quests
•	Analyze productivity trends over time
•	Improve study efficiency through adaptive recommendations
________________________________________
Features
Study Tracking
•	Record subject, duration, focus level, sleep hours, and distractions
•	Automatic productvity scoring
Gamification
•	XP and level progression
•	Daily streak tracking
•	Achievement badges
Artificial Intelligence
•	Machine Learning model predicts probability of productive sessions
•	Reinforcement Learning suggests optimal study times and subjects
Goal Management
•	Set study goals with deadlines
•	Automatic completion tracking
Pomodoro Scheduling
•	Generates study schedules based on remaining workload and deadlines
Analytics
•	Subject-wise and time-based performance insights
•	Recent productivity trends
________________________________________
Requirements
•	Python 3.8 or higher
________________________________________
Environment Setup
Step 1: Clone the Repository
git clone https://github.com/your-username/studyquest-cli.git
cd studyquest-cli
Step 2: Create a Virtual Environment (Recommended)
python -m venv venv
Activate the environment:
•	On Windows:
venv\Scripts\activate
•	On macOS/Linux:
source venv/bin/activate
________________________________________
Dependency Installation
Install required packages:
pip install scikit-learn numpy
If you skip this step, the application will still run but Machine Learning features will be disabled.
________________________________________
Project Structure
studyquest-cli/
│
├── studyquest.py        # Main application file
├── studyquest.db        # SQLite database (auto-created on first run)
├── sq_model.pkl         # Saved ML model (auto-created after training)
└── README.md
________________________________________
Running the Application
From the project directory, run:
python studyquest.py
On startup, the application will:
•	Initialize the database (if not already present)
•	Display the main menu
________________________________________
First-Time Usage Guide
1.	Run the application
2.	Select "Log Session" from the menu
3.	Enter details for a study session
4.	Repeat logging sessions to build data
5.	After a few sessions:
o	Generate daily quests
o	View analytics
o	Set study goals
Note:
•	At least 5 sessions are required before the Machine Learning model begins training.
________________________________________
Configuration
No manual configuration is required.
The application automatically manages:
•	Database file (studyquest.db)
•	Machine Learning model file (sq_model.pkl)
All data is stored locally in the project directory.
________________________________________
How the AI Components Work
Machine Learning
•	Uses a Random Forest classifier
•	Predicts whether a study session will be productive
•	Input features:
o	Time of day
o	Subject
o	Sleep hours
o	Recent productivity history
Reinforcement Learning
•	Uses Q-learning
•	Learns optimal study patterns over time
•	Adjusts recommendations based on past performance
________________________________________
Data Storage
•	SQLite database is used for persistence
•	All study sessions, goals, and user progress are stored locally
•	No external services or internet connection required
________________________________________
Limitations
•	Model performance depends on the amount of data collected
•	New subjects may initially have limited prediction accuracy
•	Command-line interface only (no graphical interface)
________________________________________
Troubleshooting
Issue: Module not found (sklearn or numpy)
Solution:
pip install scikit-learn numpy
Issue: Command not recognized (python)
Solution:
Ensure Python is installed and added to system PATH.
Issue: No quests generated
Solution:
Log at least one study session before generating quests.
________________________________________
Future Improvements
•	Modular code structure
•	Graphical user interface
•	Web-based deployment
•	Improved predictive models
•	Data export and backup functionality
________________________________________

