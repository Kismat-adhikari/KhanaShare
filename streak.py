from datetime import datetime, timedelta

USER_FILE = "user.txt"

def get_user_streak(username):
    """Retrieve the user's current streak from user.txt."""
    try:
        with open(USER_FILE, "r") as file:
            for line in file:
                user_data = line.strip().split(",")
                if user_data[1] == username:  # Assuming username is at index 1
                    return int(user_data[-1])  # Streak is the last column
        return 1  # Default streak if user not found
    except FileNotFoundError:
        return 1  # Return 1 if file doesn't exist

def update_streak(username):
    """Update the user's streak based on login activity.
    Streak increases by 1 if user logged in yesterday.
    Streak resets to 1 if user missed a day."""
    today = datetime.today().date()
    updated_lines = []
    user_found = False  

    try:
        with open(USER_FILE, "r") as file:
            for line in file:
                user_data = line.strip().split(",")
                if user_data[1] == username:
                    user_found = True
                    last_login = user_data[-2] if len(user_data) >= 9 else "2000-01-01"
                    streak = int(user_data[-1]) if len(user_data) >= 9 else 1
                    last_login_date = datetime.strptime(last_login, "%Y-%m-%d").date()
                    
                    if last_login_date == today - timedelta(days=1):
                        # User logged in yesterday, increment streak
                        streak += 1
                    elif last_login_date == today:
                        # User already logged in today, keep current streak
                        pass
                    else:
                        # User missed a day, reset streak to 1
                        streak = 1
                        
                    user_data[-2] = today.strftime("%Y-%m-%d")  # Update last login
                    user_data[-1] = str(streak)  # Update streak
                updated_lines.append(",".join(user_data))
    except FileNotFoundError:
        updated_lines = []

    # If user is new, add their entry with initial streak of 1
    if not user_found:
        updated_lines.append(f"{username},...,{today.strftime('%Y-%m-%d')},1")

    # Write back to the file
    with open(USER_FILE, "w") as file:
        file.write("\n".join(updated_lines) + "\n")