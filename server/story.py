from flask import request


def storyFinishStory():

    data = request.data
    data = {
        "playerDataDelta": {
            "deleted": {},
            "modified": {}
        }
    }

    return data

def performanceStoryStart():
    return {}, 202
