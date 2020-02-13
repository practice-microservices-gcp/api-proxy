import json
import os
import subprocess
from progress.bar import Bar

from string import Template

def getCofingValue(value):
    result = None

    with open('deploy-config.json') as file:
        config = json.load(file)

    if not value in config:
        return result
    
    if config[value] in os.environ:
        result = os.environ[config[value]]
    else:
        result = config[value]

    return result

def getListFunctions():
    with open('deploy-config.json') as file:
        config = json.load(file)

    return config['functions']


def deploy_esp():
    serviceName = getCofingValue('serviceName')
    projectId = getCofingValue('project')
    
    stream = os.popen(Template("""gcloud run deploy $serviceName \
        --image="gcr.io/endpoints-release/endpoints-runtime-serverless:2" \
        --set-env-vars=ESPv2_ARGS=--cors_preset=basic \
        --allow-unauthenticated \
        --platform managed \
        --project=$projectId 2>&1""").safe_substitute({
            "serviceName": serviceName,
            "projectId": projectId
        }))

    output= stream.read()
    lenOutput = len(output)
    startIndex = output.rfind(serviceName)

    return output[startIndex:lenOutput]

def createApiDefinition(hostEsp):
    projectId = getCofingValue('project')
    configIdMarker = 'Service Configuration ['

    with open("open-api.yml") as file:
        api_config = Template(file.read()).safe_substitute({'hostESP': hostESP})
    
    with open("open-api-tmp.yml", "w") as file:
        file.write(api_config)

    stream = os.popen(
        Template("""gcloud endpoints services deploy open-api-tmp.yml --project $projectId 2>&1""")
        .safe_substitute({'projectId': projectId})
    )

    output = stream.read()
    startIndex = output.find(configIdMarker) + len(configIdMarker)
    endIndex = output.find(']', startIndex)

    return output[startIndex:endIndex]

def getReadyNewESP(hostEsp, configId):
    projectId = getCofingValue('project')

    process = subprocess.Popen(
        ["./gcloud_build_image.sh", "-s", hostEsp, "-c",configId, "-p",projectId],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    process.communicate()



def redeployNewEsp(hostESP, configId):
    serviceName = getCofingValue('serviceName')
    projectId = getCofingValue('project')
    stream = os.popen(
        Template("""gcloud run deploy $serviceName \
            --image="gcr.io/$projectId/endpoints-runtime-serverless:$hostESP-$configId" \
            --set-env-vars=ESPv2_ARGS=--cors_preset=basic \
            --allow-unauthenticated \
            --platform managed \
            --project=$projectId""")
            .safe_substitute({
                'serviceName': serviceName,
                'projectId': projectId,
                'hostESP': hostESP,
                'configId': configId
            })
    )

    print('End redeploy ESP: {}'.format(stream.read()))



def setPermissions():
    serviceAccount = getCofingValue('serviceAccount')
    projectId = getCofingValue('project')
    functions = getListFunctions()

    for function in functions:
        stream = os.popen(
            Template("""gcloud functions add-iam-policy-binding $functionName \
                --region europe-west1 \
                --member "$serviceAccount" \
                --role "roles/cloudfunctions.invoker" \
                --project $projectId 2>&1""")
            .safe_substitute({
                'functionName': function,
                'serviceAccount': serviceAccount,
                'projectId': projectId
            })
        )
        print('Set permissions for {}'.format(function))
        print(stream.read())

def cleanProject():
    os.remove('open-api-tmp.yml')
    

bar = Bar('Deploying api', max=7)
bar.next()

hostESP = deploy_esp().strip()
bar.next()

confingId = createApiDefinition(hostESP).strip()
bar.next()

getReadyNewESP(hostESP, confingId)
bar.next()

redeployNewEsp(hostESP, confingId)
bar.next()

setPermissions()
bar.next()

cleanProject()
bar.next()

bar.finish()


