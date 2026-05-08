"""
HYLIST — NLP Bootstrap Training Data Generator (Phase 3)

Sinh labeled data cho SetFit tagger (Bug / Feature / Urgent / Research).

[LIFECYCLE — Bootstrap Only]
  Hiện tại script dùng hardcoded templates (4 labels × 15 templates).
  Khi nào nên chuyển sang real data:
  - > 500 user đã tạo task thật → chạy export_real_data.py (Phase 4)
  - Accuracy SetFit < 80% trên validation set thật → cần data thật

[GIỚI HẠN của synthetic data này]
  - 15 template/class → random.choices() tạo duplicate → model có thể overfit
  - Text không phản ánh ngôn ngữ thật của user (tiếng Anh chuẩn, không typo)
  - Chỉ đủ để cold-start, không đủ để production accuracy

[KHÔNG XÓA] Vẫn cần để:
  - Bootstrap NLP worker ở môi trường mới (không có DB prod)
  - Regression test khi refactor feature extraction
"""

import csv
import random
from pathlib import Path

# Labels support
LABELS = ["Bug", "Feature", "Urgent", "Research"]

# Mock data templates
TEMPLATES = {
    "Bug": [
        ("Fix crash on login screen", "Users report that the app crashes when clicking the login button on iOS 16."),
        ("NullPointerException in TaskService", "Exception is thrown when trying to create a task with no priority."),
        ("UI misalignment on mobile", "The sidebar menu overlaps with the main content on screens smaller than 768px."),
        ("Memory leak in dashboard", "Grafana shows memory usage climbing steadily over 24 hours without dropping."),
        ("500 Error on checkout", "Payment gateway integration throws a 500 internal server error during checkout."),
        ("Button is unresponsive", "The submit button does not work on the first click, requires multiple clicks."),
        ("Incorrect date format", "The date on the invoice is shown as MM-DD-YYYY instead of YYYY-MM-DD."),
        ("Authentication bypass vulnerability", "Users can access admin pages by modifying the JWT role claim."),
        ("Database connection timeout", "The API fails to connect to Postgres under heavy load, causing timeouts."),
        ("Typo in welcome email", "The welcome email says 'Welcom' instead of 'Welcome'."),
        ("Data not saving to local storage", "Offline mode is not persisting changes to the local SQLite database."),
        ("Screen flickering on scroll", "When scrolling through the list of tasks, the screen flickers randomly."),
        ("API rate limit exceeded too early", "The rate limiter blocks users after only 10 requests instead of 100."),
        ("Missing translations in French", "Several buttons on the settings page are still in English when French is selected."),
        ("Infinite loop in retry logic", "The worker process gets stuck in an infinite loop if the external API is down."),
    ],
    "Feature": [
        ("Add dark mode support", "Implement a dark theme toggle in the user settings using Tailwind dark mode."),
        ("Integrate with Google Calendar", "Allow users to sync their tasks and deadlines with Google Calendar."),
        ("Export reports to PDF", "Add a button to export the monthly analytics report as a PDF file."),
        ("User avatar upload", "Allow users to upload custom profile pictures instead of using default initials."),
        ("Two-factor authentication", "Implement 2FA using Google Authenticator or SMS for added security."),
        ("Kanban board view", "Add a Kanban board layout for managing tasks across different columns."),
        ("Push notifications for deadlines", "Send push notifications to mobile devices when a task is due in 24 hours."),
        ("Bulk import tasks from CSV", "Provide a feature to import hundreds of tasks at once using a CSV file template."),
        ("Rich text editor for descriptions", "Upgrade the task description field to support bold, italics, and lists."),
        ("Recurring tasks", "Allow users to set tasks to repeat daily, weekly, or monthly automatically."),
        ("Audit log dashboard", "Create a UI for admins to view the history of changes made by users."),
        ("Social login with GitHub", "Add 'Login with GitHub' as an authentication option."),
        ("Custom tags for tasks", "Let users create their own color-coded tags for organizing tasks."),
        ("Search by assignee", "Add a filter in the task list to find tasks assigned to a specific team member."),
        ("Offline mode support", "Enable users to view and edit tasks even without an internet connection."),
    ],
    "Urgent": [
        ("Production database is down", "The primary PostgreSQL instance is unreachable and failing over to replica failed."),
        ("Server returning 502 Bad Gateway", "All API endpoints are currently returning 502 errors to users."),
        ("Data breach detected", "We detected unauthorized access to the customer database from an unknown IP."),
        ("Payment gateway is failing", "All transactions are being declined, customers cannot purchase anything."),
        ("Critical security patch needed", "A zero-day vulnerability in Log4j needs to be patched immediately."),
        ("Website is completely blank", "The frontend is serving a blank white page on production."),
        ("SSL certificate expired", "The main domain SSL certificate expired 10 minutes ago, users see security warnings."),
        ("App removed from App Store", "Apple has suspended our app, we need to appeal and fix the issues ASAP."),
        ("Emails are not being sent", "The SendGrid account was suspended, no password reset emails are going out."),
        ("Massive spike in error rates", "Datadog is reporting a 1000% increase in 500 errors across all services."),
        ("Ransomware attack in progress", "Files on the shared drive are being encrypted, isolate the network immediately."),
        ("Main API domain DNS hijacked", "DNS records for our API domain were changed, traffic is being redirected."),
        ("Data corruption in users table", "A migration script corrupted the email addresses of 50,000 users."),
        ("Services crash loop", "Kubernetes nodes are out of memory and pods are constantly crashing and restarting."),
        ("AWS account compromised", "Unrecognized instances are being spun up in our AWS account."),
    ],
    "Research": [
        ("Investigate GraphQL vs REST", "Compare the performance and developer experience of moving to GraphQL."),
        ("Evaluate Vector Databases", "Research Pinecone, Milvus, and Qdrant for storing embeddings in Phase 4."),
        ("Analyze competitor pricing", "Look into how competitors structure their SaaS pricing tiers and features."),
        ("Explore LLM fine-tuning techniques", "Read papers on LoRA and QLoRA for fine-tuning open-source models."),
        ("Investigate Rust for backend services", "Build a small proof of concept to see if Rust would improve our latency."),
        ("Read up on WebSockets vs SSE", "Determine the best protocol for real-time updates in our application architecture."),
        ("Evaluate React Native vs Flutter", "Compare the two frameworks for our upcoming mobile app rewrite."),
        ("Research state management libraries", "Look into Zustand, Jotai, and Redux Toolkit for Next.js app state."),
        ("Analyze user churn reasons", "Look through support tickets to find common reasons why users cancel their subscriptions."),
        ("Investigate new AWS instance types", "See if the new Graviton processors would be cost-effective for our workloads."),
        ("Explore edge computing options", "Research Cloudflare Workers and Vercel Edge Functions for lower latency."),
        ("Study best practices for multi-tenancy", "Read up on database schema designs for isolating tenant data securely."),
        ("Evaluate BI tools", "Compare Metabase, Superset, and Looker for internal reporting dashboards."),
        ("Research GDPR compliance requirements", "Determine what changes we need to make to our data deletion processes."),
        ("Investigate caching strategies", "Look into Redis vs Memcached and different invalidation techniques."),
    ]
}

def generate_mock_data(output_file: Path, num_samples_per_class: int = 50):
    """
    Generate a CSV dataset for training SetFit.
    Duplicates some templates to reach num_samples_per_class if needed.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        
        for label, examples in TEMPLATES.items():
            # If we need more samples than templates, randomly sample with replacement
            samples = random.choices(examples, k=num_samples_per_class)
            for title, desc in samples:
                # Combine title and desc as the text feature
                text = f"{title}. {desc}"
                writer.writerow([text, label])
                
    print(f"Generated {num_samples_per_class * len(LABELS)} NLP samples to {output_file}")


if __name__ == "__main__":
    _REPO_ROOT = Path(__file__).parent.parent.parent.parent
    _OUTPUT_FILE = _REPO_ROOT / "ml" / "data" / "nlp_training.csv"
    generate_mock_data(_OUTPUT_FILE, 50)
