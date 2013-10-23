import re
import time
import configparser
import praw

# Doing a little bit of setup, here
config = configparser.ConfigParser()
config.read("llb.cfg")
username = config.get("Reddit", "username")
password = config.get("Reddit", "password")

reddit = praw.Reddit(user_agent="LazyLinkerBot by /u/blueryth/. Currently under\
     development.")
reddit.login(username, password)

# Regex for xposts in submission titles
xpost_re = re.compile('(\\br/\\w*)', re.IGNORECASE)

# Constructs regex to look for title-mentioned subreddits in comments
def build_sub_regex(subreddits):
    ret = '('
    # Loop if we're going through more than one
    if len(subreddits) > 1:
        for sub in subreddits[:1]:
            ret += '/' + sub + '|'
    ret += '/' + subreddits[-1] + ')'
    return re.compile(ret)


# Returns a list of subreddits that actually exist
def determine_valid_subs(sub_mention):
    ret = []
    for sub in sub_mention:
        try:
            reddit.get_subreddit(sub[2:], fetch=True)
            ret.append(sub)
        except Exception as e:
            print('\t' + sub + ' does not exist')
    return ret


# Checks a submission and its comments for mentions of subreddits
def is_sub_mentioned(subreddits, submission):
    sub_re = build_sub_regex(subreddits)
    # Check submission body (could be self-post)
    if submission.is_self and sub_re.findall(submission.selftext):
        print('\tFound sub mention in submission self text')
        return True

    # Check top level comments
    for comment in submission.comments:
        if sub_re.findall(comment.body):
            print('\tFound sub mention in top level comments')
            return True

    return False


# Replies to a submission with link to mentioned subreddits
def reply_to_submission(submission, mentioned_subs):
    reply = 'For the lazy: '
    if len(mentioned_subs) > 1:
        for sub in mentioned_subs[:1]:
            reply += '/' + sub + ', '
    reply += '/' + mentioned_subs[-1]
    reply += '\n\n---\nLet me know if I need to try harder: /r/LazyLinkerBot'
    submission.add_comment(reply)


# Holds the last submission we did not parse
last_submission = None

# Main execution loop
while True:
    try:
        seen = []
        for submission in reddit.get_new(
                limit=1000, 
                place_holder=last_submission):
            # If we've seen it, skip it
            if submission.fullname in seen:
                continue
            seen.append(submission.fullname)

            # Give any posting bot a 30 second window to make a comment
            if abs(submission.created_utc - time.time()) < 30:
                last_submission = submission
                continue

            # Check titles for xposts
            title_hits = xpost_re.findall(submission.title)
            if title_hits:
                print('Found sub mentions in title: ' + 
                        submission.fullname + ' ' + submission.title)
                real_subs = determine_valid_subs(title_hits)
                if len(real_subs) > 0 and 
                        not is_sub_mentioned(real_subs, submission):
                    print('\tNo mention in top comments; replying.')
                    reply_to_submission(submission, real_subs)
    except praw.errors.RateLimitExceeded as rle:
        print('Moved too quick, sleeping: ', rle.sleep_time)
        time.sleep(rle.sleep_time)
        continue
    except:
        raise

    time.sleep(60)