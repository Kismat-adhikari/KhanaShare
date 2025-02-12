from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g
from flask_socketio import SocketIO, join_room, leave_room, send, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import os
import json
from streak import get_user_streak, update_streak



app = Flask(__name__)
app.secret_key = 'my-secret-key-here'  # Change this to a secure secret key

# Initialize Flask-SocketIO
socketio = SocketIO(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# This ensure the instance folder exists if not it creates it
os.makedirs('instance', exist_ok=True)
USER_FILE = 'instance/user.txt'
MESSAGE_FILE = 'instance/messages.txt'
FOLLOW_FILE = 'instance/follows.txt'
NOTIFICATION_FILE = 'instance/notifications.txt'

# File initialization functions
def init_user_file():
    if not os.path.exists(USER_FILE):
        with open(USER_FILE, 'w') as f:
            pass

def init_message_file():
    if not os.path.exists(MESSAGE_FILE):
        with open(MESSAGE_FILE, 'w') as f:
            pass

def init_follow_file():
    if not os.path.exists(FOLLOW_FILE):
        with open(FOLLOW_FILE, 'w') as f:
            pass

def init_notification_file():
    if not os.path.exists(NOTIFICATION_FILE):
        with open(NOTIFICATION_FILE, 'w') as f:
            pass




def get_streak():
    """Get streak for the current user."""
    if 'username' in session:
        return get_user_streak(session['username'])
    return 0

@app.context_processor
def inject_streak():
    """Make streak available to all templates."""
    return dict(streak=get_streak())
# User management functions

def save_user(user_data):
    with open(USER_FILE, 'a') as f:
        f.write(','.join(user_data) + '\n')

# Message management functions
def get_messages(room):
    try:
        with open(MESSAGE_FILE, 'r') as f:
            return [line.strip().split('|') for line in f.readlines() if line.startswith(room)]
    except FileNotFoundError:
        return []

def save_message(room, sender, message):
    with open(MESSAGE_FILE, 'a') as f:
        f.write(f'{room}|{sender}|{message}\n')

# Follow management functions
def get_followers(username):
    try:
        with open(FOLLOW_FILE, 'r') as f:
            return [line.strip().split(',')[0] for line in f.readlines() if line.strip().split(',')[1] == username]
    except FileNotFoundError:
        return []

def get_following(username):
    try:
        with open(FOLLOW_FILE, 'r') as f:
            return [line.strip().split(',')[1] for line in f.readlines() if line.strip().split(',')[0] == username]
    except FileNotFoundError:
        return []

def is_following(follower, following):
    try:
        with open(FOLLOW_FILE, 'r') as f:
            return any(line.strip() == f"{follower},{following}" for line in f.readlines())
    except FileNotFoundError:
        return False

def add_follower(follower, following):
    if not is_following(follower, following):
        with open(FOLLOW_FILE, 'a') as f:
            f.write(f"{follower},{following}\n")
        return True
    return False

def remove_follower(follower, following):
    try:
        with open(FOLLOW_FILE, 'r') as f:
            lines = f.readlines()
        
        with open(FOLLOW_FILE, 'w') as f:
            for line in lines:
                if line.strip() != f"{follower},{following}":
                    f.write(line)
        return True
    except FileNotFoundError:
        return False

# Updated Notification functions
def get_notifications(username, unread_only=False):
    try:
        notifications = []
        seen_follow_actions = set()  # Track unique follow actions
        
        with open(NOTIFICATION_FILE, 'r') as f:
            for line in f.readlines():
                try:
                    parts = line.strip().split('|')
                    if len(parts) < 3:  # Skip malformed lines
                        continue
                        
                    recipient = parts[0]
                    if recipient != username:
                        continue
                        
                    # Parse notification data
                    try:
                        notification_data = json.loads(parts[1])
                    except json.JSONDecodeError:
                        continue  # Skip invalid JSON
                        
                    timestamp = parts[2]
                    is_read = len(parts) > 3 and parts[3] == 'read'
                    
                    # For follow notifications, only keep the most recent one from each user
                    if notification_data['type'] == 'follow':
                        actor = notification_data['actor']
                        if actor in seen_follow_actions:
                            continue
                        seen_follow_actions.add(actor)
                    
                    notifications.append({
                        'username': recipient,
                        'data': notification_data,
                        'timestamp': timestamp,
                        'read': is_read
                    })
                except Exception:
                    continue  # Skip any problematic lines
        
        # Sort notifications by timestamp, newest first
        notifications.sort(key=lambda x: datetime.strptime(x['timestamp'], '%Y-%m-%d %H:%M:%S'), reverse=True)
        
        if unread_only:
            return [n for n in notifications if not n['read']]
        return notifications
            
    except FileNotFoundError:
        return []


def update_or_create_notification(username, actor, action_type, additional_data=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification_data = {
        'type': action_type,
        'actor': actor,
        **(additional_data or {})
    }
    
    try:
        # Read existing notifications
        with open(NOTIFICATION_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        existing_notification_updated = False
        
        for line in lines:
            try:
                parts = line.strip().split('|')
                if len(parts) < 3:  # Skip malformed lines
                    continue
                    
                current_username = parts[0]
                if current_username != username:
                    new_lines.append(line)
                    continue
                
                try:
                    current_data = json.loads(parts[1])
                except json.JSONDecodeError:
                    continue
                
                # For follow notifications, update existing one from the same actor
                if (action_type == 'follow' and 
                    current_data.get('type') == 'follow' and 
                    current_data.get('actor') == actor):
                    new_lines.append(f"{username}|{json.dumps(notification_data)}|{timestamp}|unread\n")
                    existing_notification_updated = True
                else:
                    new_lines.append(line)
            except Exception:
                continue
        
        # If we didn't update an existing notification, create a new one
        if not existing_notification_updated:
            new_lines.append(f"{username}|{json.dumps(notification_data)}|{timestamp}|unread\n")
        
        # Write back all notifications
        with open(NOTIFICATION_FILE, 'w') as f:
            f.writelines(new_lines)
            
        return True
    except Exception as e:
        print(f"Error updating notification: {e}")
        return False
    


def save_notification(username, message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(NOTIFICATION_FILE, 'a') as f:
        f.write(f"{username}|{message}|{timestamp}|unread\n")

def mark_notifications_as_read(username):
    try:
        with open(NOTIFICATION_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            try:
                parts = line.strip().split('|')
                if len(parts) < 3:  # Skip malformed lines
                    continue
                    
                if parts[0] == username and (len(parts) <= 3 or parts[3] == 'unread'):
                    # Make sure we have exactly 4 parts with 'read' status
                    base_parts = parts[:3]
                    new_lines.append(f"{('|').join(base_parts)}|read\n")
                else:
                    new_lines.append(line)
            except Exception:
                continue
                
        with open(NOTIFICATION_FILE, 'w') as f:
            f.writelines(new_lines)
        return True
    except FileNotFoundError:
        return False

# Configure upload folder
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'mp4'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(title):
    return secure_filename(title.lower().replace(' ', '_'))

@app.route('/post', methods=['GET', 'POST'])
def post_list():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            hashtags = request.form.get('hashtags', '').split(',')
            categories = request.form.get('categories', '').split(',')
            
            # Handle file upload
            if 'media' not in request.files:
                flash('No file selected')
                return redirect(request.url)
                
            file = request.files['media']
            if file.filename == '':
                flash('No file selected')
                return redirect(request.url)
                
            if file and allowed_file(file.filename):
                # Create sanitized filename based on title
                file_extension = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{sanitize_filename(title)}.{file_extension}"
                
                # Ensure upload directory exists
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                
                # Save the file
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                
                # Prepare post data
                post_data = {
                    "title": title,
                    "description": description,
                    "media": f"{UPLOAD_FOLDER}/{filename}",
                    "hashtags": [tag for tag in hashtags if tag],
                    "tags": [cat for cat in categories if cat],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                
                # Add new post to posts.txt
                with open('posts.txt', 'a') as f:
                    f.write(json.dumps(post_data) + '\n')
                
                return redirect(url_for('index'))
            else:
                flash('Invalid file type')
                return redirect(request.url)
                
        except Exception as e:
            print(f"Error creating post: {str(e)}")
            flash('Error creating post. Please try again.')
            return redirect(request.url)
    
    return render_template('post.html')

#routes
@app.route('/')
def index():
    if 'email' in session:
        # Load posts for the feed
        posts = []
        if os.path.exists('posts.txt'):
            with open('posts.txt', 'r') as f:
                posts = [json.loads(line) for line in f if line.strip()]
        # Sort posts by timestamp (newest first)
        posts.sort(key=lambda x: datetime.strptime(x['timestamp'], "%Y-%m-%d %H:%M"), reverse=True)
        return render_template('index.html', posts=posts)
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        display_name = request.form['display_name'].capitalize()  # Capitalize the first letter
        cook_type = request.form['cook_type']
        experience = request.form['experience']
        age = request.form['age']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        users = get_users()

        if any(user[1] == username for user in users):
            flash('Username already exists')
            return redirect(url_for('signup'))

        if any(user[7] == email for user in users):  # Updated index for email
            flash('Email already exists')
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        user_data = [full_name, username, display_name, cook_type, experience, age, phone, email, hashed_password]
        save_user(user_data)

        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['email_or_username']
        password = request.form['password']

        users = get_users()
        # Print for debugging
        print("Login attempt:", login_input)
        print("Available users:", users)
        
        user = None
        for u in users:
            # Check if we have enough fields
            if len(u) >= 9:  # Updated to account for new experience field
                if u[7] == login_input or u[1] == login_input:  # Check email (index 7) or username (index 1)
                    user = u
                    break

        if user and check_password_hash(user[8], password):  # Updated index for password hash
            session['email'] = user[7]  # Updated index for email
            session['username'] = user[1]
            
            update_streak(user[1])
            
            flash('Login successful!')
            return redirect(url_for('profile'))

        flash('Incorrect email/username or password')
        return redirect(url_for('login'))

    return render_template('login.html')

# Helper function to get users - updated to handle different field counts
def get_users():
    try:
        with open(USER_FILE, 'r') as f:
            users = []
            for line in f:
                user = line.strip().split(',')
                # Ensure we have the correct number of fields
                if len(user) < 9:  # If we don't have enough fields
                    # Add experience field if it's missing
                    if len(user) == 8:  # Old format without experience
                        user.insert(4, 'beginner')  # Insert experience after cook_type
                users.append(user)
            return users
    except FileNotFoundError:
        return []
    



@app.route('/streak')
def streak():
    if 'username' not in session:
        flash('You must be logged in to see your streak.')
        return redirect(url_for('login'))

    username = session['username']
    user_streak = get_user_streak(username)  

    return render_template('streak.html', streak=user_streak)



@app.route('/is_following/<username>')
def check_following_status(username):
    if 'username' not in session:
        return jsonify({'is_following': False})
    
    current_user = session['username']
    is_following_user = is_following(current_user, username)
    
    return jsonify({'is_following': is_following_user})

# Updated notification routes
@app.route('/notifications')
def notifications():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    notifications = get_notifications(username)
    
    # Format notifications for display
    formatted_notifications = []
    for notif in notifications:
        notification_data = notif['data']
        if notification_data['type'] == 'follow':
            message = f"{notification_data['actor']} started following you"
        else:
            message = notification_data.get('message', 'Unknown notification')
            
        formatted_notifications.append({
            'message': message,
            'timestamp': notif['timestamp'],
            'read': notif['read'],
            'type': notification_data['type'],
            'actor': notification_data['actor']
        })
    
    # Mark all as read
    mark_notifications_as_read(username)
    
    return render_template('notifications.html', 
                         notifications=formatted_notifications,
                         is_following=is_following)




@app.route('/api/notifications')
def get_user_notifications():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    username = session['username']
    unread_notifications = get_notifications(username, unread_only=True)
    
    formatted_notifications = []
    for notif in unread_notifications:
        notification_data = notif['data']
        if notification_data['type'] == 'follow':
            message = f"{notification_data['actor']} started following you"
        else:
            message = notification_data.get('message', 'Unknown notification')
            
        formatted_notifications.append({
            'message': message,
            'timestamp': notif['timestamp'],
            'type': notification_data['type'],
            'actor': notification_data['actor']
        })
    
    return jsonify({
        'success': True,
        'notifications': formatted_notifications
    })






@app.route('/profile')
@app.route('/profile/<username>')
def profile(username=None):
    if 'email' not in session:
        return redirect(url_for('login'))

    users = get_users()
    
    # If no username is provided, show current user's profile
    if username is None:
        user = next((user for user in users if user[7] == session['email']), None)  # Using email index 7
        is_own_profile = True
    else:
        user = next((user for user in users if user[1] == username), None)  # Using username index 1
        is_own_profile = user is not None and user[7] == session['email']  # Compare emails

    if user:
        # Convert user list to dictionary for easier template access
        user_dict = {
            'full_name': user[0],
            'username': user[1],
            'display_name': user[2],
            'cook_type': user[3],
            'experience': user[4],
            'age': user[5],
            'phone': user[6],
            'email': user[7],
            'bio': "No bio yet"  # Default bio
        }

        # Get bio from bio.txt if it exists
        if os.path.exists('bio.txt'):
            try:
                with open('bio.txt', 'r') as f:
                    bios = json.load(f)
                    user_dict['bio'] = bios.get(user_dict['username'], '').strip() or "No bio yet"
            except (json.JSONDecodeError, FileNotFoundError):
                user_dict['bio'] = "No bio yet"  # Default if error occurs

        followers = get_followers(user[1])
        following = get_following(user[1])
        is_following_user = is_following(session['username'], user[1]) if not is_own_profile else False

        return render_template('profile.html',
                             user=user_dict,
                             is_own_profile=is_own_profile,
                             followers_count=len(followers),
                             following_count=len(following),
                             is_following=is_following_user)

    return "User not found", 404


@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    users = get_users()
    user = next((user for user in users if user[7] == session['email']), None)
    
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            bio = data.get('bio', '').strip()
            username = user[1]  # Get username from user tuple
            
            # Create or update bio file
            bios = {}
            bio_file = 'bio.txt'
            
            # Read existing bios if file exists
            if os.path.exists(bio_file):
                with open(bio_file, 'r') as f:
                    try:
                        bios = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            # Update bio for current user
            bios[username] = bio
            
            # Save updated bios
            with open(bio_file, 'w') as f:
                json.dump(bios, f, indent=4)
            
            return jsonify({'success': True})
            
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    
    # For GET request, prepare user data for the template
    user_dict = {
        'full_name': user[0],
        'username': user[1],
        'display_name': user[2],
        'cook_type': user[3],
        'experience': user[4],
        'age': user[5],
        'phone': user[6],
        'email': user[7],
        'bio': "No bio yet"  # Default bio
    }
    
    # Get bio if exists
    if os.path.exists('bio.txt'):
        try:
            with open('bio.txt', 'r') as f:
                bios = json.load(f)
                user_dict['bio'] = bios.get(user_dict['username'], '').strip() or "No bio yet"
        except (json.JSONDecodeError, FileNotFoundError):
            user_dict['bio'] = "No bio yet"  # Default if error occurs

    return render_template('edit_profile.html', user=user_dict)
@app.route('/friends')
def friends():
    return render_template('friends.html')



@app.route('/follow/<username>', methods=['POST'])
def follow_user(username):
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})

    current_user = session['username']
    
    if current_user == username:
        return jsonify({'success': False, 'message': 'You cannot follow yourself'})

    if add_follower(current_user, username):
        followers_count = len(get_followers(username))
        following_count = len(get_following(username))
        
        # Create or update follow notification
        update_or_create_notification(
            username=username,
            actor=current_user,
            action_type='follow'
        )
        
        # Emit notification update
        socketio.emit('notification_update', {
            'username': username
        }, broadcast=True)
        
        return jsonify({
            'success': True,
            'message': f'You are now following {username}',
            'followers_count': followers_count,
            'following_count': following_count
        })
    
    return jsonify({'success': False, 'message': 'Already following'})



@app.route('/unfollow/<username>', methods=['POST'])
def unfollow_user(username):
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})

    current_user = session['username']
    
    if remove_follower(current_user, username):
        followers_count = len(get_followers(username))
        following_count = len(get_following(username))
        
        socketio.emit('follow_update', {
            'follower': current_user,
            'following': username,
            'action': 'unfollow',
            'followers_count': followers_count,
            'following_count': following_count
        }, broadcast=True)
        
        return jsonify({
            'success': True,
            'message': f'You have unfollowed {username}',
            'followers_count': followers_count,
            'following_count': following_count
        })
    
    return jsonify({'success': False, 'message': 'Not following'})

@app.route('/message')
def message_list():
    if 'email' not in session:
        return redirect(url_for('login'))
    
    current_username = session['username']
    users_with_messages = {}
    
    try:
        with open(MESSAGE_FILE, 'r') as f:
            for line in f:
                room, sender, message = line.strip().split('|')
                user1, user2 = room.split('_')
                
                other_user = user2 if current_username == user1 else user1
                if current_username in (user1, user2):
                    users_with_messages[other_user] = {
                        'username': other_user,
                        'last_message': message
                    }
    except FileNotFoundError:
        pass
    
    users = list(users_with_messages.values())
    return render_template('message.html', users=users)




@app.route('/message/<username>', methods=['GET'])
def message_user(username):
    if 'email' not in session:
        return redirect(url_for('login'))

    current_username = session['username']
    room = f"{current_username}_{username}" if current_username < username else f"{username}_{current_username}"
    messages = get_messages(room)

    return render_template('chat.html', username=username, room=room, messages=messages)

@app.route('/get_follow_counts/<username>')
def get_follow_counts(username):
    followers = get_followers(username)
    following = get_following(username)
    return jsonify({
        'followers_count': len(followers),
        'following_count': len(following)
    })

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# SocketIO Events
@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)

@socketio.on('leave')
def on_leave(data):
    username = data['username']
    room = data['room']
    leave_room(room)
    send(f"{username} has left the room.", to=room)

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    message = data['message']
    sender = session['username']
    save_message(room, sender, message)
    send(f"{sender}: {message}", to=room)

@app.route('/streak-info')
def streak_info():
    # If user is logged in, get their streak
    streak = 0
    if 'username' in session:
        streak = get_user_streak(session['username'])
    return render_template('streak_info.html', streak=streak)


@app.route('/search_users')
def search_users():
    query = request.args.get('query', '').lower()
    if not query:
        return jsonify({'users': []})
    
    users = get_users()
    current_user = session.get('username')
    
    # Filter users based on search query
    matching_users = []
    for user in users:
        # user[0] is full_name, user[1] is username
        if query in user[0].lower() or query in user[1].lower():
            # Skip the current user in search results
            if user[1] != current_user:
                matching_users.append({
                    'full_name': user[0],
                    'username': user[1],
                    'is_following': is_following(current_user, user[1]) if current_user else False
                })
    
    return jsonify({'users': matching_users})


from social_connections import (
    get_user_followers,
    get_user_following,
    format_user_list,
    get_follow_counts
)

@app.route('/api/followers/<username>')
def get_followers_list(username):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    followers = get_user_followers(username)
    formatted_users = format_user_list(followers, session['username'])
    
    return jsonify({
        'users': formatted_users
    })

@app.route('/api/following/<username>')
def get_following_list(username):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    following = get_user_following(username)
    formatted_users = format_user_list(following, session['username'])
    
    return jsonify({
        'users': formatted_users
    })
if __name__ == '__main__':
    init_user_file()
    init_message_file()
    init_follow_file()
    init_notification_file()
    socketio.run(app, debug=True)