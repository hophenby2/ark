from flask import request


def storyFinishStory():
    json_body = request.get_json()

    data = {
        "playerDataDelta": {
            "modified": {
                "status": {
                    "flags": {
                        json_body["stageId"]: 1
                    }
                }
            },
            "deleted": {}
        }
    }

    return data

def performanceStoryStart():
    return {}, 202
