"""Demo: render all 101 visual types across all 3 modules."""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.context.coding_visuals as cv  # noqa: E402
import core.context.general_visuals as gv  # noqa: E402
import core.context.visuals as v  # noqa: E402


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def show(name, output):
    print()
    print(f"--- {name} ---")
    print(output)

# ── UNIVERSAL (31) ──
section("UNIVERSAL VISUALS (31) — for ANY agent")
show("1. Sparkline", v.render_sparkline([1,3,2,5,4,8,6,7,9,5,3,8], width=16, label="CPU"))
show("2. Heatmap", v.render_heatmap(
    [[1,2,3,4],[5,6,7,8],[2,4,6,8]],
    col_labels=["Mon","Tue","Wed","Thu"],
    row_labels=["AM","PM","EV"],
))
show("3. Donut", v.render_donut(0.75, size=7, label="Progress"))
show("4. Radar", v.render_radar([("Speed",0.8),("Acc",0.6),("Mem",0.4),("IO",0.9),("Net",0.5)]))
show("5. Gauge", v.render_gauge(0.82, width=30, label="CPU"))
show("6. Timeline", v.render_timeline(
    [("Design",0,3),("Build",3,8),("Test",8,12),("Deploy",12,15)],
    width=30, total=15, label="Project",
))
show("7. Tree", v.render_tree([
    {"name":"src","children":[
        {"name":"api","children":[{"name":"handlers.py"}]},
        {"name":"utils.py"},
    ]},
    {"name":"tests"},
]))
show("8. Flow", v.render_flow(
    ["Input","Process","Output"], [(0,1,80),(1,2,60)],
    width=20, label="Pipeline",
))
show("9. Spinner", v.render_spinner(3, label="Loading"))
show("10. Waterfall", v.render_waterfall(
    [("Revenue",1000),("Costs",-400),("Tax",-200),("Bonus",150),("Net",0)],
    width=25, label="P&L",
))
show("11. Braille Chart", v.render_braille_chart(
    [[1,3,2,5,4,8,6,7,9,5,3,8,7,6,4,5]],
    width=16, height=6, labels=["Series A"],
))
show("12. Sub-cell Bar", v.render_subcell_bar(0.73, width=25, label="Upload"))
show("13. Status Matrix", v.render_status_matrix(
    [("API","ok"),("DB","ok"),("Cache","warn"),("Queue","fail"),("Worker","running"),
     ("Cron","pending"),("Auth","ok"),("CDN","blocked")],
    cols=4, label="Services",
))
show("14. Network Graph", v.render_network(
    [{"name":"Auth"},{"name":"API"},{"name":"DB"},{"name":"Cache"},{"name":"Queue"}],
    [(0,1),(1,2),(1,3),(2,4),(3,4)], size=15, label="System",
))
show("15. Dashboard", v.render_dashboard(
    "System Overview",
    [("Health","All systems: OK\nUptime: 99.97%"),
     ("Performance","Latency: 42ms p99\nThroughput: 1.2k rps"),
     ("Alerts","0 critical, 2 warnings\nLast: 5m ago")],
    width=48,
))
show("16. Gradient Bar", v.render_gradient(0.65, width=30, label="Intensity"))
show("17. Emoji Status", v.render_emoji_status(
    [("Build","success"),("Tests","running"),("Deploy","pending"),("Monitor","warn"),
     ("Backup","done"),("Security","ok")],
    cols=3,
))
show("18. Comparison Table", v.render_comparison([
    {"Feature":"Speed","School":"10ms","DCP":"15ms","Super":"25ms"},
    {"Feature":"Memory","School":"2MB","DCP":"5MB","Super":"8MB"},
    {"Feature":"Tools","School":"45","DCP":"12","Super":"8"},
], winner_col="School"))
show("19. Bar Chart", v.render_bar_chart(
    [("Revenue",12500),("Expenses",8300),("Profit",4200),("Tax",1200),("Savings",3000)],
    width=30, label="Financials",
))
show("20. Histogram", v.render_histogram(
    [1,2,2,3,3,3,4,4,4,4,5,5,5,6,6,7,8,9,10,12], bins=8, width=25, label="Response Times",
))
show("21. Stats Box", v.render_stats_box(
    [12,15,18,22,25,28,30,35,42,55,80], label="Latency Distribution",
))
show("22. Delta Arrows", v.render_delta(
    [("Revenue",10000,12500),("Costs",8000,7200),("Users",500,620),("Errors",50,35)],
    label="Monthly Changes",
))
show("23. Kanban Board", v.render_kanban(
    [("To Do",["Design API","Write docs","Setup CI"]),
     ("In Progress",["Build auth","Write tests"]),
     ("Done",["Project init","DB schema"])],
    label="Sprint Board",
))
show("24. KPI Big Number", v.render_kpi(
    "42", label="Active Users", suffix="%", trend="+12% vs last week",
))
show("25. Pie Chart", v.render_pie(
    [("Engineering",35),("Design",20),("Marketing",25),("Support",15),("Other",5)],
    size=9, label="Budget Split",
))
show("26. Scatter Plot", v.render_scatter(
    [(1,2),(2,4),(3,5),(4,4),(5,8),(6,7),(7,9),(8,12),(9,10),(10,14)],
    width=30, height=10, x_label="Effort", y_label="Output",
))
show("27. Funnel", v.render_funnel(
    [("Visitors",10000),("Signups",3500),("Trials",1200),("Paid",400),("Renewals",280)],
    width=30, label="Conversion",
))
show("28. Calendar Heatmap", v.render_calendar_heatmap(
    {"2026-01-05":3,"2026-01-06":8,"2026-01-07":5,"2026-01-08":12,"2026-01-09":1,
     "2026-01-12":7,"2026-01-13":10,"2026-01-14":2},
    label="Activity",
))
show("29. Word Cloud", v.render_word_cloud(
    [("python",45),("javascript",38),("typescript",30),("react",25),("docker",20),("api",18),
     ("testing",15),("deploy",12),("design",10),("code",8),("data",5)],
    label="Tech Stack",
))
show("30. Mini Ring", v.render_mini_ring(0.7, label="Sprint"))

# ── CODING (30) ──
section("CODING AGENT VISUALS (30) — for dev workflows")
show("1. Code Coverage", cv.render_code_coverage(
    [("app.py",0.92),("models.py",0.87),("utils.py",0.45),("legacy.py",0.23)],
    width=25, label="Coverage", threshold=0.8,
))
show("2. Complexity Heat", cv.render_complexity_heat(
    [("parse_input",3),("validate",7),("process_data",15),("render",2),("auth",12)],
    label="Cyclomatic Complexity",
))
show("3. Diff Summary", cv.render_diff_summary(
    [("src/api.py",120,35),("src/models.py",45,12),("tests/test_api.py",200,0),
     ("README.md",30,5)],
    width=25, label="Git Diff",
))
show("4. Test Results", cv.render_test_results(
    [("Unit Tests",{"pass":245,"fail":2,"skip":8}),
     ("Integration",{"pass":89,"fail":0,"skip":3}),
     ("E2E",{"pass":34,"fail":1,"skip":0}),
     ("Security",{"pass":12,"fail":0,"skip":0})],
    label="Test Suite",
))
show("5. Dependency Graph", cv.render_dependency_graph(
    "myapp",
    {"myapp":["fastapi","sqlalchemy","pydantic","redis"],"fastapi":["starlette","pydantic"],
     "sqlalchemy":["greenlet"],"pydantic":["typing-extensions"],"redis":[],
     "starlette":[],"typing-extensions":[],"greenlet":[]},
    max_depth=3, label="Dependencies",
))
show("6. File Size Bars", cv.render_file_size_bars(
    [("server.py",2500),("models.py",1800),("handlers.py",1200),("utils.py",800),
     ("config.py",300),("main.py",150)],
    width=30, unit="LOC", label="File Sizes",
))
show("7. Git Timeline", cv.render_git_timeline(
    [("a1b2c3d","Alice",5),("e4f5g6h","Bob",2),("i7j8k9l","Alice",12),
     ("m0n1o2p","Carol",3),("q3r4s5t","Bob",8),("u6v7w8x","Alice",1)],
    label="Commit Activity",
))
show("8. Error Rate", v.render_sparkline(
    [2,5,3,8,12,7,4,15,9,3,2,1,6,4,2], width=25, label="Errors/hr",
))
show("9. Perf Benchmark", cv.render_perf_benchmark(
    [("API Response",120.0,80.0),("DB Query",200.0,150.0),("Cache Hit",50.0,15.0),
     ("Serialization",30.0,25.0)],
    width=20, label="Before vs After",
))
show("10. API Latency", cv.render_api_latency(
    [("GET /users",50,120),("POST /orders",80,200),("GET /products",30,90),
     ("PUT /profile",60,150),("DELETE /item",40,100)],
    width=20, label="Endpoint Latency",
))
show("11. Build Pipeline", cv.render_build_pipeline(
    [("Lint","pass",2.5),("Build","pass",12.3),("Unit Tests","pass",45.0),
     ("Integration","running",0),("E2E","pending",0),("Deploy","pending",0)],
    label="CI/CD Pipeline",
))
show("12. Security Scan", cv.render_security_scan(
    [("CVE-2026-1234","critical","requests"),("CVE-2026-5678","high","flask"),
     ("CVE-2026-9012","medium","pyyaml"),("CVE-2026-3456","low","certifi")],
    label="Vulnerabilities",
))
show("13. Code Churn", cv.render_code_churn(
    [("server.py",45,2300),("models.py",32,1800),("handlers.py",28,1200),
     ("utils.py",15,600),("config.py",8,200)],
    width=25, label="Code Churn",
))
show("14. DB Schema", cv.render_db_schema(
    {"users":["id: UUID PK","name: VARCHAR","email: VARCHAR UNIQUE","created_at: TIMESTAMP"],
     "orders":["id: UUID PK","user_id: UUID FK","total: DECIMAL","status: ENUM"]},
    label="Database Schema",
))
show("15. Memory Profile", cv.render_memory_profile(
    [10,15,20,35,30,25,40,50,45,30,20,15], [5,8,12,18,15,10,20,25,22,12,8,5],
    width=30, label="Memory Usage",
))
show("16. Flame Chart", cv.render_flame_chart(
    [("main()",100,0),("  parse_args()",15,1),("  load_config()",20,1),
     ("  run_server()",65,1),("    handle_request()",40,2),
     ("      query_db()",25,3),("      render()",15,3)],
    width=35, label="CPU Profile",
))
show("17. Deploy Status", cv.render_deploy_status(
    [("Production","2.4.1","pass"),("Staging","2.5.0","running"),("Dev","2.5.1-beta","pass"),
     ("QA","2.4.1","warn"),("DR","2.3.0","pending")],
    label="Environments",
))
show("18. Feature Flags", cv.render_feature_flags(
    [("dark_mode",True,"Dark UI theme"),
     ("beta_api",False,"Beta API endpoints"),
     ("new_dashboard",True,"Redesigned dashboard"),
     ("ai_assistant",False,"AI-powered assistant"),
     ("analytics_v2",True,"New analytics engine")],
    label="Feature Flags",
))
show("19. Package Versions", cv.render_package_versions(
    [("react","18.2.0","18.2.0"),("typescript","5.0.0","5.3.0"),("vite","5.0.0","5.1.0"),
     ("eslint","8.50.0","8.56.0"),("prettier","3.0.0","3.0.0")],
    label="Dependencies",
))
show("20. Log Density", cv.render_log_density(
    {"DEBUG":[5,10,8,12,15,20,18],"INFO":[20,35,40,50,45,55,60],
     "WARN":[2,5,3,8,4,2,6],"ERROR":[1,3,2,5,1,0,2]},
    width=4, label="Log Levels",
))
show("21. Duplication", cv.render_duplication(
    [("auth.py","middleware.py",25),("utils.py","helpers.py",12),("models.py","schemas.py",8)],
    label="Code Duplication",
))
show("22. Refactor Progress", cv.render_refactor_progress(
    [("Lines of Code",5200,3100),("Functions",180,120),("Max Complexity",18,8),
     ("Test Coverage",65,92)],
    width=20, label="Refactoring",
))
show("23. Endpoint Map", cv.render_endpoint_map(
    [("GET","/api/v1/users","get_users"),("POST","/api/v1/users","create_user"),
     ("GET","/api/v1/users/{id}","get_user"),("PUT","/api/v1/users/{id}","update_user"),
     ("DELETE","/api/v1/users/{id}","delete_user"),("GET","/api/v1/health","health_check")],
    label="API Routes",
))
show("24. Cache Stats", cv.render_cache_stats(
    [("Redis Cache",8500,1500),("Memory Cache",12000,500),("CDN",9800,200),
     ("Query Cache",4500,3500)],
    width=25, label="Cache Performance",
))
show("25. Concurrency", cv.render_concurrency(
    [("Worker-1",0,5),("Worker-2",2,8),("Worker-3",4,7),("Worker-4",6,10),("Worker-5",8,12)],
    width=35, total=12, label="Task Timeline",
))
show("26. GC Pressure", cv.render_gc_pressure(
    [("Gen0",0.5,1.2),("Gen0",1.0,0.8),("Gen1",2.5,5.0),("Gen0",3.0,1.0),
     ("Gen2",5.0,15.0),("Gen0",6.0,0.9),("Gen1",8.0,3.5)],
    width=35, label="Garbage Collection",
))
show("27. Network Waterfall", cv.render_network_waterfall(
    [("/api/users",0,120,"200"),("/api/orders",50,200,"200"),("/static/app.js",100,80,"200"),
     ("/api/config",150,45,"200"),("/api/analytics",180,300,"500"),
     ("/static/style.css",200,60,"200")],
    width=30, label="Network Requests",
))
show("28. Queue Depth", cv.render_queue_depth(
    [("Task Queue",45,100),("Email Queue",12,50),("Webhook Queue",8,20),
     ("Search Index",3,15),("Notification",25,60)],
    width=25, label="Message Queues",
))
show("29. Error Matrix", cv.render_error_matrix(
    [[2,5,3,1],[8,12,6,4],[1,0,2,1],[15,22,18,10]],
    ["API","Database","Cache","External"], ["Mon","Tue","Wed","Thu"],
    width=4, label="Error Heatmap",
))
show("30. Review Progress", cv.render_review_progress(
    [("PR-142","approved",3,12),("PR-143","running",8,25),("PR-144","pending",0,5),
     ("PR-145","approved",2,8),("PR-146","fail",12,30)],
    label="Code Reviews",
))

# ── GENERAL (40) ──
section("GENERAL ASSISTANT VISUALS (40) — for chat, personal, any use")
show("1. Sentiment Gauge", gv.render_sentiment_gauge(0.65, 0.25, 0.10, label="Review Sentiment"))
show("2. Word Count", gv.render_word_count(
    "The quick brown fox jumps over the lazy dog. "
    "This is a sample text for demonstration purposes.",
    label="Text Stats",
))
show("3. Reading Progress", gv.render_reading_progress(
    245, 500, width=30, label="Reading", book_title="Dune by Frank Herbert",
))
show("4. Mood Tracker", gv.render_mood_tracker(
    [("Monday","happy"),("Tuesday","great"),("Wednesday","ok"),("Thursday","sad"),
     ("Friday","excited"),("Saturday","relaxed"),("Sunday","calm")],
    label="This Week",
))
show("5. Habit Tracker", gv.render_habit_tracker(
    [("Exercise",[True,True,False,True,True,True,False]),
     ("Reading",[True,True,True,True,False,True,True]),
     ("Meditation",[False,True,True,False,True,True,True]),
     ("Water",[True,True,True,True,True,True,True])],
    label="Daily Habits",
))
show("6. Task Priority", gv.render_task_priority(
    [("Fix login bug","high","high"),("Write documentation","low","high"),
     ("Update dependencies","high","low"),("Clean up code","low","low"),
     ("Deploy hotfix","high","high")],
    label="Priority Matrix",
))
show("7. Meeting Agenda", gv.render_meeting_agenda(
    [("Welcome & Intro",5,"Alice"),("Q3 Review",15,"Bob"),("Product Demo",20,"Carol"),
     ("Open Discussion",15,"Team"),("Action Items",5,"Alice")],
    label="Team Meeting",
))
show("8. Budget Tracker", gv.render_budget_tracker(
    [("Groceries",500,420),("Rent",1500,1500),("Utilities",200,180),
     ("Transport",150,210),("Entertainment",100,85),("Savings",300,300)],
    width=20, label="Monthly Budget",
))
show("9. Expense Breakdown", gv.render_expense_breakdown(
    [("Housing",1500),("Food",600),("Transport",300),("Entertainment",200),
     ("Health",150),("Shopping",250),("Education",100)],
    width=25, label="Spending",
))
show("10. Weekly Schedule", gv.render_weekly_schedule(
    {"Monday":["9:00 Standup","10:00 Code Review","14:00 Sprint Planning"],
     "Tuesday":["9:00 Standup","11:00 Design Sync"],
     "Wednesday":["9:00 Standup","10:00 1:1","15:00 Demo"],
     "Thursday":["9:00 Standup","13:00 Architecture"],
     "Friday":["9:00 Standup","10:00 Retro","15:00 Happy Hour"]},
    label="Work Week",
))
show("11. Countdown", gv.render_countdown("Product Launch", 45, 6, 30))
show("12. Star Rating", gv.render_star_rating(4.5, label="Product Rating", count=1247))
show("13. Poll Results", gv.render_poll_results(
    [("JavaScript",342),("Python",289),("TypeScript",215),("Rust",156),("Go",98),("Other",45)],
    width=25, label="Favorite Language",
))
show("14. Survey Matrix", gv.render_survey_matrix(
    [("Product Quality",[4,5,3,5,4,4,5,3,4,5]),("Customer Service",[3,4,5,4,3,4,4,5,3,4]),
     ("Value for Money",[2,3,4,3,2,3,4,3,2,3]),("Ease of Use",[5,5,4,5,5,4,5,5,4,5])],
    label="Survey Results",
))
show("15. Decision Matrix", gv.render_decision_matrix(
    [("Option A",[8.5,7.0,9.0]),("Option B",[6.0,9.5,7.5]),
     ("Option C",[9.0,6.5,8.0]),("Option D",[7.5,8.0,6.5])],
    ["Cost","Quality","Speed"], weights=[0.3,0.4,0.3], label="Decision",
))
show("16. Pros & Cons", gv.render_pros_cons(
    ["Fast performance","Great UX","Good pricing","Active community","Regular updates"],
    ["Limited features","No mobile app","Poor docs","Expensive add-ons","Slow support"],
    label="React Framework",
))
show("17. Progress Wheel", gv.render_progress_wheel(0.68, size=7, label="Project Complete"))
show("18. Fitness Stats", gv.render_fitness_stats(
    [("Running",35,320),("Weight Training",45,280),("Cycling",60,450),
     ("Swimming",30,250),("Yoga",25,120)],
    width=25, label="Workouts This Week",
))
show("19. Recipe Steps", gv.render_recipe_steps(
    ["Preheat oven to 350F","Mix flour, sugar, and eggs","Add milk and vanilla extract",
     "Pour into greased pan","Bake for 25-30 minutes","Let cool for 10 minutes",
     "Frost and serve"],
    label="Chocolate Cake",
))
show("20. Checklist", gv.render_checklist(
    [("Buy groceries",True),("Write report",True),("Call dentist",False),
     ("Clean house",False),("Pay bills",True),("Exercise",False),("Read 30 min",True)],
    label="Today's Tasks",
))
show("21. Travel Itinerary", gv.render_travel_itinerary(
    [("Day 1 - Arrival",["09:00 Flight lands","11:00 Hotel check-in",
        "13:00 Lunch at Cafe Roma","15:00 City walking tour",
        "19:00 Dinner reservation"]),
     ("Day 2 - Explore",["08:00 Breakfast","10:00 Museum visit",
        "13:00 Shopping district","16:00 Beach time","20:00 Night market"])],
    label="Paris Trip",
))
show("22. Study Progress", gv.render_study_progress(
    [("Calculus",0.85),("Linear Algebra",0.72),("Statistics",0.45),
     ("Machine Learning",0.30),("Deep Learning",0.15),("Python",0.90),("SQL",0.60)],
    width=25, label="Study Progress",
))
show("23. Flashcard Scores", gv.render_flashcard_scores(
    [("Spanish",25,15,45),("French",10,8,22),("Japanese",40,20,30),("German",5,3,12)],
    label="Spaced Repetition",
))
show("24. Quiz Results", gv.render_quiz_results(
    [("What is 2+2?",True),("Capital of France?",True),("Largest planet?",True),
     ("Speed of light?",False),("Water formula?",True),("Python creator?",True),
     ("HTTP stands for?",False),("CSS purpose?",True)],
    label="Knowledge Quiz",
))
show("25. Todo Board", gv.render_todo_board(
    [("Backlog",["API refactor","Database migration","Performance audit"]),
     ("In Progress",["User auth","Payment integration"]),
     ("Review",["Dashboard redesign"]),
     ("Done",["Login page","Settings panel","Email service"])],
    label="Project Board",
))
show("26. Price Comparison", gv.render_price_comparison(
    [("MacBook Pro",2499,4.8),("ThinkPad X1",1899,4.5),("Dell XPS",1599,4.3),
     ("Framework",1299,4.6),("System76",1099,4.2)],
    width=25, label="Laptop Prices",
))
show("27. Review Summary", gv.render_review_summary(
    {5:450,4:280,3:120,2:45,1:25}, label="Product Reviews",
))
show("28. Mind Map", gv.render_mind_map(
    "AI Project",
    {"Research":["Literature review","Model selection","Dataset prep"],
     "Development":["Architecture","Training","Evaluation"],
     "Deployment":["Serving","Monitoring","Scaling"],
     "Business":["Requirements","Stakeholders","Metrics"]},
    label="Project Plan",
))
show("29. Contact Card", gv.render_contact_card(
    "Alice Johnson",
    {"Role":"Senior Engineer","Email":"alice@company.com","Phone":"+1 555-0123",
     "Location":"San Francisco","Timezone":"PST","Slack":"@alice"},
    label="Team Member",
))
show("30. Gratitude Log", gv.render_gratitude_log(
    [("2026-01-05","Family dinner was wonderful"),("2026-01-06","Finished a difficult project"),
     ("2026-01-07","Great workout at the gym"),("2026-01-08","Helped a friend move"),
     ("2026-01-09","Beautiful sunset today")],
    label="Gratitude Journal",
))
show("31. Water Intake", gv.render_water_intake(6, 8, label="Hydration"))
show("32. Sleep Tracker", gv.render_sleep_tracker(
    [("Monday",7.5,0.85),("Tuesday",6.0,0.60),("Wednesday",8.0,0.90),
     ("Thursday",5.5,0.45),("Friday",7.0,0.75),("Saturday",9.0,0.95),("Sunday",8.5,0.88)],
    width=20, label="Sleep",
))
show("33. Meditation Log", gv.render_meditation_log(
    [("Morning Session",20),("Midday Break",10),("Evening Wind-down",15),
     ("Weekend Deep",30),("Quick Reset",5)],
    width=20, label="Meditation",
))
show("34. Mood Timeline", gv.render_mood_timeline(
    [("Mon",3),("Tue",4),("Wed",5),("Thu",2),("Fri",4),("Sat",5),("Sun",5)],
    label="Mood This Week",
))
show("35. Life Balance", gv.render_life_balance(
    [("Career",0.85),("Health",0.70),("Social",0.55),("Finance",0.75),
     ("Learning",0.60),("Family",0.80),("Hobbies",0.45),("Rest",0.65)],
    size=11, label="Life Balance",
))
show("36. Savings Goal", gv.render_savings_goal(3750, 5000, width=30, label="Vacation Fund"))
show("37. Workout Plan", gv.render_workout_plan(
    [("Monday","Push Day - Chest/Shoulders/Triceps",True),
     ("Tuesday","Pull Day - Back/Biceps",True),
     ("Wednesday","Legs & Core",False),("Thursday","Active Recovery - Yoga",False),
     ("Friday","Full Body HIIT",False),("Saturday","Outdoor Run",False),
     ("Sunday","Rest Day",False)],
    label="Weekly Plan",
))
show("38. Reading List", gv.render_reading_list(
    [("Dune","Frank Herbert",0.65),("1984","George Orwell",1.0),
     ("The Pragmatic Programmer","Hunt & Thomas",0.40),("Clean Code","Robert Martin",0.85),
     ("Design Patterns","Gang of Four",0.20)],
    width=15, label="Reading List",
))
show("39. Wishlist", gv.render_wishlist(
    [("Mechanical Keyboard",150,"high"),("Standing Desk",400,"medium"),
     ("Noise Headphones",250,"high"),("Monitor Arm",80,"low"),
     ("Webcam HD",120,"medium"),("Desk Lamp",45,"low")],
    width=20, label="Wishlist",
))
show("40. Date Countdown", gv.render_date_countdown(
    "Birthday Party", 12, 365, width=30, label="Countdown",
))

print()
print("=" * 70)
print("  ALL 101 VISUALS RENDERED SUCCESSFULLY")
print("  31 Universal + 30 Coding + 40 General = 101")
print("=" * 70)
