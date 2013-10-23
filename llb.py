import re
import time
import configparser
import praw

# Doing a little bit of setup, here
config = configparser.ConfigParser()
config.read("llb.cfg")
username = config.get("Reddit", "username")
password = config.get("Reddit", "password")

reddit = praw.Reddit(user_agent="LazyLinkerBot by /u/blueryth/. Generates \
    links to subreddits from submission titles where needed. Currently under \
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
        for submission in reddit.get_new(place_holder=last_submission):
            print('' + submission.fullname + ' ' + submission.title)

            # Give any posting bot a 20 second window to make a comment
            if abs(submission.created_utc - time.time()) < 20:
                last_submission = submission
                continue

            # Check titles for xposts
            title_hits = xpost_re.findall(submission.title)
            if title_hits:
                print('\tFound sub mentions in title: '
                    + submission.fullname + ' ' + submission.title)
                real_subs = determine_valid_subs(title_hits)
                if len(real_subs) > 0:
                    # Check top-level comments for any mentions
                    mentioned = False
                    comment_re = build_sub_regex(real_subs)
                    for comment in submission.comments:
                        if comment_re.findall(comment.body):
                            mentioned = True
                            print('\t\tFound sub mention in top level comments')
                            break

                    if not mentioned:
                        print('\t\tNo mention, in top comments; replying.')
                        reply_to_submission(submission, real_subs)
                else:
                    print('\tNo mentioned subs exist')

    except Exception as e:
        print(e)

    time.sleep(30)