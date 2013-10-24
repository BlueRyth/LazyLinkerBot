import re
import time
import configparser
import praw

# Doing a little bit of setup, here
config = configparser.ConfigParser()
config.read('llb.cfg')
username = config.get('LazyLinkerBot', 'username')
password = config.get('LazyLinkerBot', 'password')

reddit = praw.Reddit(user_agent='LazyLinkerBot by /u/blueryth/')
reddit.login(username, password)

# Regex for xposts in submission titles
xpost_re = re.compile('(\\br/\\w*)', re.IGNORECASE)

# Dictionary of subs where we've been rate-limited. We'll give them a chance to
# cool down
sleep_subs = {}

# Maximum number of subscribers to repost a subreddit
max_sub_size = config.get('LazyLinkerBot', 'maxsubsize')

# Constructs regex to look for any title-mentioned subreddits
def build_sub_regex(subreddits):
    ret = '('
    # Loop if we're going through more than one
    if len(subreddits) > 1:
        for sub in subreddits[:1]:
            ret += '/' + sub + '|'
    ret += '/' + subreddits[-1] + ')'
    return re.compile(ret, re.IGNORECASE)

# Checks if mentioned subreddit exists
def does_mention_exist(subreddit):
    try:
        # If the fetch fails, the subreddit does not exist. This is the
        # PRAW way of doing it, apparently.
        reddit.get_subreddit(subreddit, fetch=True)
    except:
        print('[Ignore] /r/' + subreddit + ' does not exist')
        return False
    else:
        return True

# Checks if subreddit mention is in the mentioned subreddit, hah!
def is_self_mention(subreddit, submission):
    if subreddit.lower() == submission.subreddit.display_name.lower():
        print('[Ignore] /r/' + subreddit + ' is self-mentioned')
        return True
    return False

# Checks if submission is a link to the mentioned subreddit
def is_link_to_mention(subreddit, submission):
    sub = '/r/' + subreddit
    if sub.lower() in submission.url.lower():
        print('[Ignore] Submission is link to mention')
        return True
    return False

# Checks if mention is too popular to be a useful link
def is_mention_too_popular(subreddit):
    try:
        if reddit.get_subreddit(subreddit).subscribers > max_sub_size:
            print('[Ignore] /r/' + subreddit + ' is too popular')
            return True
    except:
        pass
    return False

# Returns a list of subreddits that we could post about
def determine_valid_subs(sub_mention, submission):
    ret = []
    for sub in sub_mention:
        if (does_mention_exist(sub[2:]) and 
                not is_self_mention(sub[2:], submission) and
                not is_link_to_mention(sub[2:], submission) and
                not is_mention_too_popular(sub[2:])):
            ret.append(sub)
    return ret

# Checks a submission and its comments for mentions of subreddits
def is_sub_mentioned(subreddits, submission):
    sub_re = build_sub_regex(subreddits)
    # Check submission body (could be self-post)
    if submission.is_self and sub_re.findall(submission.selftext):
        print('[Ignore] Found sub mention in submission self text')
        return True

    # Check top level comments
    for comment in submission.comments:
        if sub_re.findall(comment.body):
            print('[Ignore] Found sub mention in top level comments')
            return True

    return False

# Replies to a submission with link to mentioned subreddits
def reply_to_submission(submission, mentioned_subs):
    reply = 'For the lazy: '
    if len(mentioned_subs) > 1:
        for sub in mentioned_subs[:1]:
            reply += '/' + sub + ', '
    reply += '/' + mentioned_subs[-1]
    reply += '\n\n---\nI provide direct links to lesser known cross-posted \
            subs if one isn\'t provided.\n\nLet me know if I need to try \
            harder: /r/LazyLinkerBot'
    submission.add_comment(reply)

# Checks if we're safe to post on a subreddit
def can_post_to_subreddit(sub_name):
    if sub_name in sleep_subs.keys() and time.time() < sleep_subs[sub_name]:
            return False
    return True

# Sets rate limit on subreddit, so we won't try again
def set_rate_limit(sub_name, cooldown):
    sleep_subs[sub_name] = time.time() + cooldown

# Holds the last submission we did not parse
last_submission = None

# Main execution loop
while True:
    try:
        seen = []
        for submission in reddit.get_subreddit('all').get_new(
                limit=1000, 
                place_holder=last_submission):

            sub_name = submission.subreddit.display_name
            if not can_post_to_subreddit(sub_name):
                last_submission = submission
                continue

            # If we've seen it, skip it. Sometimes we'll see the same submission
            # without letting the cache clear, and we'll double comment =/
            if submission.fullname in seen:
                continue
            seen.append(submission.fullname)

            # Give anybody posting a 30 second window to make a link
            if abs(submission.created_utc - time.time()) < 30:
                last_submission = submission
                continue

            # Check titles for xposts
            title_hits = xpost_re.findall(submission.title)
            if title_hits:
                print('[Submission] ' + 
                        submission.fullname + ' ' + submission.title + 
                        ' in /r/' + sub_name)
                valid_subs = determine_valid_subs(title_hits, submission)
                if len(valid_subs) > 0 and not is_sub_mentioned(
                        valid_subs, 
                        submission):
                    print('[Reply] No mention; replying.')
                    try:
                        reply_to_submission(submission, valid_subs)
                    except praw.errors.RateLimitExceeded as rle:
                        print(
                                '[WHOA] Moved too quickly on /r/' + 
                                sub_name + ':', rle.sleep_time)
                        set_rate_limit(sub_name, rle.sleep_time)

    except:
        raise

    time.sleep(60)
