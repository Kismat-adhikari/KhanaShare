def get_user_followers(username):
    """Get list of users who follow the given username."""
    try:
        with open('instance/follows.txt', 'r') as f:
            followers = []
            for line in f:
                follower, following = line.strip().split(',')
                if following == username:
                    followers.append(follower)
            return followers
    except FileNotFoundError:
        return []

def get_user_following(username):
    """Get list of users that the given username follows."""
    try:
        with open('instance/follows.txt', 'r') as f:
            following = []
            for line in f:
                follower, followed = line.strip().split(',')
                if follower == username:
                    following.append(followed)
            return following
    except FileNotFoundError:
        return []

def get_user_details(username):
    """Get user details from user.txt file."""
    try:
        with open('instance/user.txt', 'r') as f:
            for line in f:
                user = line.strip().split(',')
                if user[1] == username:  # username is at index 1
                    return {
                        'full_name': user[0],
                        'username': user[1],
                        'display_name': user[2],
                        'cook_type': user[3]
                    }
    except FileNotFoundError:
        return None

def is_following(follower, username):
    """Check if follower is following username."""
    try:
        with open('instance/follows.txt', 'r') as f:
            return any(line.strip() == f"{follower},{username}" for line in f)
    except FileNotFoundError:
        return False

def format_user_list(usernames, current_user):
    """Format list of usernames into detailed user information."""
    formatted_users = []
    for username in usernames:
        user_details = get_user_details(username)
        if user_details:
            user_details['is_following'] = is_following(current_user, username)
            formatted_users.append(user_details)
    return formatted_users

def get_follow_counts(username):
    """Get follower and following counts for a user."""
    followers = get_user_followers(username)
    following = get_user_following(username)
    return {
        'followers_count': len(followers),
        'following_count': len(following)
    }