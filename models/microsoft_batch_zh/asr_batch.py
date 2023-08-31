#!/usr/bin/env python3
# Request and swagger_client module must be installed.
# Run pip install requests if necessary.
# doc: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-transcription

import codecs
import json
import requests
import swagger_client
import sys
import time

MAX_RETRY = 10
RETRY_INTERVAL = 1.0
REGION = 'chinaeast2'
LOCALE = "zh-CN"
NAME = "Microsoft batch transcription"
DESCRIPTION = "Microsoft batch transcription description"

with open('SUBSCRIPTION_KEY', 'r') as f:
    SUBSCRIPTION_KEY = f.readline().strip()


def recognize(audio):
    text = ''
    for i in range(MAX_RETRY):
        try:
            rec = do_recognition(audio)
            if rec != '':
                text = rec
                break
        except Exception as e:
            sys.stderr.write("exception, retrying:{}\n".format(str(e)))
            sys.stderr.flush()
            time.sleep(RETRY_INTERVAL)
    return text


def do_recognition(audio):
    text = ''

    # configure API key authorization: subscription_key
    configuration = swagger_client.Configuration()
    configuration.api_key["Ocp-Apim-Subscription-Key"] = SUBSCRIPTION_KEY
    configuration.host = "https://{REGION}.api.cognitive.azure.cn/speechtotext/v3.1".format(REGION=REGION)

    # create the client object and authenticate
    client = swagger_client.ApiClient(configuration)

    # create an instance of the transcription api class
    api = swagger_client.CustomSpeechTranscriptionsApi(api_client=client)

    # Specify transcription properties by passing a dict to the properties parameter. See
    # https://learn.microsoft.com/azure/cognitive-services/speech-service/batch-transcription-create?pivots=rest-api#request-configuration-options
    # for supported parameters.
    properties = swagger_client.TranscriptionProperties()
    properties.profanity_filter_mode = "None"

    # Use base models for transcription. Comment this block if you are using a custom model.
    transcription_definition = do_transcription_definition(audio, properties)

    created_transcription, status, headers = api.transcriptions_create_with_http_info(transcription=transcription_definition)

    # get the transcription Id from the location URI
    transcription_id = headers["location"].split("/")[-1]

    # Log information about the created transcription. If you should ask for support, please
    # include this information.
    print("Created new transcription with id '{transcription_id}' in region {REGION}".format(transcription_id=transcription_id,REGION=REGION))
    print("Checking status.")

    completed = False
    while not completed:
        # wait for 5 seconds before refreshing the transcription status
        time.sleep(5)
        transcription = api.transcriptions_get(transcription_id)
        print("Transcriptions status: {status}.".format(status=transcription.status))
        if transcription.status in ("Failed", "Succeeded"):
            completed = True

        if transcription.status == "Succeeded":
            pag_files = api.transcriptions_list_files(transcription_id)
            for file_data in _paginate(api, pag_files):
                if file_data.kind != "Transcription":
                    continue

                results_url = file_data.links.content_url
                results = requests.get(results_url)
                results_object = json.loads(results.content.decode('utf-8'))
                recognizedPhrases = results_object['recognizedPhrases']
                if len(recognizedPhrases) > 0:
                    nBest = recognizedPhrases[0]['nBest']
                    text = nBest[0]['lexical']
                else:
                    print("Transcriptions result is null.")
        elif transcription.status == "Failed":
            sys.stderr.write("Transcription failed: {message}".format(message=transcription.properties.error.message))
            sys.stderr.flush()

    print("Transcriptions text: {text}".format(text=text))

    # Delete transcription
    api.transcriptions_delete(transcription_id)
    print("Deleted transcription with id {transcription_id}.\n".format(transcription_id=transcription_id))

    return text


def do_transcription_definition(uri, properties):
    """
    Transcribe a single audio file located at `uri` using the settings specified in `properties`
    using the base model for the specified locale.
    """
    transcription_definition = swagger_client.Transcription(
        display_name=NAME,
        description=DESCRIPTION,
        locale=LOCALE,
        content_urls=[uri],
        properties=properties
    )

    return transcription_definition


def _paginate(api, paginated_object):
        """
        The autogenerated client does not support pagination. This function
        returns a generator over all items of the array
        that the paginated object `paginated_object` is part of.
        """
        yield from paginated_object.values
        typename = type(paginated_object).__name__
        auth_settings = ["api_key"]
        while paginated_object.next_link:
            link = paginated_object.next_link[len(api.api_client.configuration.host):]
            paginated_object, status, headers = api.api_client.call_api(link, "GET", response_type=typename, auth_settings=auth_settings)
            if status == 200:
                yield from paginated_object.values
            else:
                error_message = "Could not receive paginated data: status {status}".format(status=status)
                sys.stderr.write(error_message)
                sys.stderr.flush()
                raise Exception(error_message)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.stderr.write("asr_batch.py <in_scp> <out_trans>\n")
        exit(-1)
    scp = codecs.open(sys.argv[1], 'r',  'utf8')
    trans = codecs.open(sys.argv[2], 'w+', 'utf8')

    n = 0
    for l in scp:
        l = l.strip()
        if (len(l.split('\t')) == 2):  # scp format: "key\taudio"
            key, audio = l.split(sep="\t", maxsplit=1)
            print(str(n) + '\tkey:' + key + '\taudio:' + audio)

            text = ''
            text = recognize(audio)

            trans.write(key + '\t' + text + '\n')
            trans.flush()
            n += 1
        else:
            sys.stderr.write("Invalid line: " + l + "\n")
            sys.stderr.flush()

    scp.close()
    trans.close()
