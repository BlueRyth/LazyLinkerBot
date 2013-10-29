import os
import re
import time
import configparser

import praw

# Doing a little bit of setup, here
config = configparser.ConfigParser()
config.read("llb.cfg")

# Maximum number of subscribers to repost a subreddit
max_sub_size = config.get("LazyLinkerBot", "maxsubsize")

# Log formats
xpost_log = config.get("LazyLinkerBot", "xpostlog")
reply_log = config.get("LazyLinkerBot", "replylog")
banned_log = config.get("LazyLinkerBot", "bannedlog")
ignore_log = config.get("LazyLinkerBot", "ignorelog")
ratelimit_log = config.get("LazyLinkerBot", "ratelimitlog")

# Reply format. ConfigParser has OS issues reading \n out of values =/
reply = "For the lazy: {subs}\n\n---\nI provide direct links to lesser known"\
        " subs mentioned in the title if one isn\'t already provided.\n\nLet"\
        " me know if I need to try harder: /r/LazyLinkerBot"

# Logins
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")
if (username is None or password is None):
    raise Exception("Expecting reddit username and password in env vars")

# Setup PRAW reddit object
reddit = praw.Reddit(user_agent="LazyLinkerBot by /u/blueryth/")
reddit.login(username, password)

# Regex for xposts in submission titles
xpost_re = re.compile("(\\br/\\w*)", re.IGNORECASE)

# Dictionary of subs where we"ve been rate-limited. We"ll give them a chance 
# to cool down
sleep_subs = {}

# Banned subs. Some people don"t love me :(
banned_subs = []

# Holds the last submission we did not parse
last_submission = None

# Active submission
active_submission = None

def log_submission_ignore(reason):
    """Logs out ignoring a submission for a specific reason"""
    global active_submission
    if active_submission is not None:
        print(ignore_log.format(reason=reason,
            fullname=active_submission.fullname,
            title=active_submission.title,
            subreddit=active_submission.subreddit))


def build_sub_regex(subreddits):
    """Constructs regex to look for list of passed-in subreddit names"""
    ret = "("
    if len(subreddits) > 1:
        for sub in subreddits[:1]:
            ret += "/" + sub + "|"
    ret += "/" + subreddits[-1] + ")"
    return re.compile(ret, re.IGNORECASE)


def does_mention_exist(subreddit):
    """Checks if subreddit exists"""
    try:
        # PRAW lazily instantiates subreddits, so we won't know if its real
        # unless we attempt a fetch. It will fail if the sub doesn"t exist
        reddit.get_subreddit(subreddit, fetch=True)
    except:
        log_submission_ignore("Subreddit does not exit")
        return False
    else:
        return True


def is_self_mention(subreddit, submission):
    """Checks if subreddit mention is in the mentioned subreddit, hah!"""
    if subreddit.lower() == submission.subreddit.display_name.lower():
        log_submission_ignore("Submission in mentioned subreddit")
        return True
    return False


def is_link_to_mention(subreddit,   submission):
    """Checks if submission is a link to the mentioned subreddit"""
    sub = "/r/" + subreddit
    if sub.lower() in submission.url.lower():
        log_submission_ignore("Submission is link to mentioned subreddit")
        return True
    return False


def is_mention_too_popular(subreddit):
    """Checks if subreddit is too popular to be a useful link"""
    if reddit.get_subreddit(subreddit).subscribers > int(max_sub_size):
        log_submission_ignore("Subreddit is too popular")
        return True
    return False


def determine_valid_subs(sub_mention, submission):
    """Determines list of subreddits that we should mention"""
    ret = []
    for sub in sub_mention:
        sub_name = sub[2:]
        if (does_mention_exist(sub_name) and 
                not is_self_mention(sub_name, submission) and
                not is_link_to_mention(sub_name, submission) and
                not is_mention_too_popular(sub_name)):
            ret.append(sub)
    return ret


def is_sub_mentioned(subreddits, submission):
    """Checks for mentions of subreddits in a submission and its comments"""
    sub_re = build_sub_regex(subreddits)
    # Check submission body (could be self-post)
    if submission.is_self and sub_re.findall(submission.selftext):
        log_submission_ignore("Mentioned subreddit in submission self text")
        return True
    # Check top level comments
    for comment in submission.comments:
        if sub_re.findall(comment.body):
            log_submission_ignore("Mentioned subreddit in top level comments")
            return True
    return False


def reply_to_submission(submission, mentioned_subs):
    """Replies to a submission with link to mentioned subreddits"""
    reply_subs = ""
    if len(mentioned_subs) > 1:
        for sub in mentioned_subs[:1]:
            reply_subs += "/" + sub.lower() + ", "
    reply_subs += "/" + mentioned_subs[-1].lower()
    try:
        submission.add_comment(reply.format(subs=reply_subs))
    except Exception:
        raise


def can_post_to_subreddit(sub_name):
    """Checks if we"re safe to post to a subreddit"""
    if (not sub_name in banned_subs and
        sub_name in sleep_subs.keys() and 
        time.time() < sleep_subs[sub_name]):
            return False
    return True


def is_banned(sub_name):
    """Checks if our account is banned on a subreddit"""
    if reddit.get_subreddit(sub_name).user_is_banned:
        if not sub_name in banned_subs:
            print(banned_log.format(subreddit="/r/" + sub_name))
            banned_subs.append(sub_name)
        return True
    return False


def set_rate_limit(sub_name, cooldown):
    """Sets cooldown on a subreddit for the duration of a rate limit"""
    sleep_subs[sub_name] = time.time() + cooldown

def lazy_linker_duties():
    """Performs the lazy linker duties of checking submissions for xposts"""
    global last_submission
    global active_submission
    seen = []
    for submission in reddit.get_subreddit("all").get_new(limit=1000,
            place_holder=last_submission):
        active_submission = submission
        sub_name = submission.subreddit.display_name
        if not can_post_to_subreddit(sub_name):
            last_submission = submission
            continue
        # If we"ve seen it, skip it. Sometimes we"ll see the same 
        # submission without letting the cache clear, and we"ll double 
        # comment =/
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
            print(xpost_log.format(fullname=submission.fullname,
                title=submission.title,
                subreddit=submission.subreddit))
            valid_subs = determine_valid_subs(title_hits, submission)
            if (len(valid_subs) > 0 and 
                    not is_sub_mentioned(valid_subs,submission) and
                    not is_banned(sub_name)):
                print(reply_log.format(fullname=submission.fullname,
                    title=submission.title,
                    subreddit=submission.subreddit))
                try:
                    reply_to_submission(submission, valid_subs)
                except praw.errors.RateLimitExceeded as rle:
                    print(ratelimit_log.format(
                        subreddit=submission.subreddit))
                    set_rate_limit(sub_name, rle.sleep_time)

# Main execution loop
while True:
    start_time = time.time()
    try:
        lazy_linker_duties()
    except Exception:
        raise
    # Wait for the 60-second cache expiration
    delay = time.time() - start_time
    if delay < 60:
        time.sleep(delay)
        