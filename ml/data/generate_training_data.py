"""
HYLIST — Synthetic Training Data Generator (Bootstrap)

[LIFECYCLE NOTE]
  Giai đoạn    | Data strategy
  ------------ | -----------------------------------------------
  0 user       | Script này sinh 10,000 synthetic tasks (hiện tại)
  > 100 user   | Export từ DB + blend với synthetic (50/50)
  > 1,000 user | Real data chiếm 90%, synthetic dùng augment edge case
  Mature       | Script vẫn giữ — dùng để bootstrap môi trường mới / test

[KHÔNG XÓA FILE NÀY] Dù có user thật, vẫn cần script này để:
  - Train model ở môi trường CI/CD mà không có DB prod
  - Tạo data cho unit test ML pipeline
  - Benchmark regression khi thay đổi features

Phân phối (Distribution Requirements):
1. Không dùng random uniform (vì không phản ánh thực tế).
2. priority_score: Phân phối Pareto (nhiều task thường, ít task quan trọng).
3. estimated_time: Log-normal distribution (đa số 1-4h, rất ít >20h).
4. actual_time:
   - Đa số mọi người underestimate (actual > estimated).
   - Task càng to càng dễ trễ hạn.
5. status: Tỉ lệ done (65%), in_progress (15%), review (5%), todo (10%), cancelled (5%).
6. tags: [Bug, Feature, Urgent, Research] - có liên quan đến priority và actual_time.
"""

import os
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# Seed để reproducible
np.random.seed(42)
Faker.seed(42)
fake = Faker()

NUM_TASKS = 10000
# File đã nằm trong ml/data/ → output cùng thư mục
OUTPUT_DIR = os.path.dirname(__file__)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "tasks_training.csv")


def generate_training_data():
    print(f"Generating {NUM_TASKS} mock tasks...")
    
    # 1. IDs & Cơ bản
    task_ids = [str(uuid.uuid4()) for _ in range(NUM_TASKS)]
    project_ids = [str(uuid.uuid4()) for _ in range(50)]  # 50 projects
    org_ids = [str(uuid.uuid4()) for _ in range(10)]      # 10 orgs
    assignee_ids = [str(uuid.uuid4()) for _ in range(100)] # 100 users

    # 2. Priority Score (Pareto distribution: 1 -> 5)
    # Lật ngược pareto: đa số 1-2, ít 5
    raw_priority = np.random.pareto(a=2.0, size=NUM_TASKS)
    # Scale & clip vào khoảng [1, 5]
    priority_scores = np.clip(np.floor(raw_priority + 1), 1, 5).astype(int)
    # Đảo ngược để có phân phối hợp lý hơn nếu cần, nhưng thường 3 là default, 5 là cao.
    # Cho majority là 3, sau đó 2, 4, 1, 5
    p_weights = [0.1, 0.2, 0.4, 0.2, 0.1]
    priority_scores = np.random.choice([1, 2, 3, 4, 5], size=NUM_TASKS, p=p_weights)

    # 3. Estimated Time (Log-normal distribution)
    # Đa số từ 1-8 giờ
    mu, sigma = 1.0, 0.75 # mean = exp(mu + sigma^2/2) ~ 3.6h
    estimated_times = np.random.lognormal(mu, sigma, NUM_TASKS)
    estimated_times = np.clip(np.round(estimated_times, 1), 0.5, 100.0)

    # 4. Actual Time (Underestimation bias)
    # Nếu task to -> estimate càng sai
    # actual_time = estimated_time * N(1.2, 0.3)
    bias_mean = 1.1 + (estimated_times / 40.0)  # Càng dài càng bias
    bias_std = 0.2 + (estimated_times / 100.0)
    actual_times = estimated_times * np.random.normal(bias_mean, bias_std)
    actual_times = np.clip(np.round(actual_times, 1), 0.1, 150.0)

    # 5. Status
    # Cần set actual_time = NaN cho những task chưa done/cancelled (đang làm dở)
    statuses = np.random.choice(
        ["todo", "in_progress", "review", "done", "cancelled"], 
        size=NUM_TASKS, 
        p=[0.10, 0.15, 0.05, 0.65, 0.05]
    )
    
    # Xóa actual_time của task chưa xong
    actual_times_clean = []
    for st, act in zip(statuses, actual_times):
        if st in ["done", "cancelled"]:
            actual_times_clean.append(act)
        else:
            actual_times_clean.append(np.nan)

    # 6. Tags (Dựa trên rule)
    tags_list = []
    for i in range(NUM_TASKS):
        tags = []
        if priority_scores[i] == 5:
            tags.append("Urgent")
            # Urgent task thường là Bug
            if np.random.rand() < 0.6:
                tags.append("Bug")
        if "Bug" not in tags and np.random.rand() < 0.3:
            tags.append("Bug")
        elif "Bug" not in tags and np.random.rand() < 0.5:
            tags.append("Feature")
        
        if estimated_times[i] > 20:
            tags.append("Research")
            
        if not tags:
            tags.append("Task")
            
        tags_list.append(",".join(tags))

    # 7. Timestamps
    now = datetime.now()
    created_ats = []
    updated_ats = []
    deadlines = []
    
    for i in range(NUM_TASKS):
        # Create from 1 to 90 days ago
        days_ago = np.random.randint(1, 90)
        created = now - timedelta(days=days_ago)
        
        # Deadline usually 1-14 days after creation
        deadline = created + timedelta(days=np.random.randint(1, 14))
        
        # Updated recently
        updated = created + timedelta(days=np.random.randint(0, days_ago)) if days_ago > 0 else created
        
        created_ats.append(created.strftime("%Y-%m-%dT%H:%M:%SZ"))
        updated_ats.append(updated.strftime("%Y-%m-%dT%H:%M:%SZ"))
        deadlines.append(deadline.strftime("%Y-%m-%dT%H:%M:%SZ"))

    # 8. Titles & Descriptions
    print("Generating text data (might take a minute)...")
    titles = []
    descriptions = []
    for i in range(NUM_TASKS):
        if "Bug" in tags_list[i]:
            title = fake.sentence(nb_words=6).replace(".", "")
            titles.append(f"Fix: {title}")
        elif "Feature" in tags_list[i]:
            title = fake.sentence(nb_words=5).replace(".", "")
            titles.append(f"Implement {title}")
        else:
            titles.append(fake.sentence(nb_words=6).replace(".", ""))
            
        descriptions.append(fake.paragraph(nb_sentences=3))

    # Create DataFrame
    df = pd.DataFrame({
        "id": task_ids,
        "org_id": np.random.choice(org_ids, NUM_TASKS),
        "project_id": np.random.choice(project_ids, NUM_TASKS),
        "assignee_id": np.random.choice(assignee_ids, NUM_TASKS),
        "title": titles,
        "description": descriptions,
        "status": statuses,
        "priority_score": priority_scores,
        "estimated_time": estimated_times,
        "actual_time": actual_times_clean,
        "tags": tags_list,
        "created_at": created_ats,
        "updated_at": updated_ats,
        "deadline": deadlines,
    })

    # Đảm bảo thư mục tồn tại
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Lưu CSV
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {NUM_TASKS} mock tasks at: {OUTPUT_FILE}")
    
    # Hiển thị thống kê
    print("\n--- DATA DISTRIBUTION STATS ---")
    print("\n1. Status Distribution:")
    print(df["status"].value_counts(normalize=True).round(3) * 100)
    
    print("\n2. Priority Score Distribution:")
    print(df["priority_score"].value_counts(normalize=True).round(3) * 100)
    
    print("\n3. Estimated vs Actual Time (Completed tasks only):")
    completed = df[df["status"].isin(["done", "cancelled"])]
    print(f"Mean Estimated: {completed['estimated_time'].mean():.2f}h")
    print(f"Mean Actual:    {completed['actual_time'].mean():.2f}h")
    print(f"Underestimation: {(completed['actual_time'].mean() / completed['estimated_time'].mean() - 1) * 100:.1f}%")

if __name__ == "__main__":
    generate_training_data()
