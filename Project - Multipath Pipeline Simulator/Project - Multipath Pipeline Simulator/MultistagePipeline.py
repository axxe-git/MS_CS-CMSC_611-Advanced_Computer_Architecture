'''
Created on Apr 5, 2014

@author: axxe
'''
import io
import collections
from collections import defaultdict
import Queue
import re
from copy import deepcopy

class MultistagePipeline(object):
    '''
    classdocs
    '''

    def __init__(self, configFilePath, instrFilePath, registerFilePath, instructionSetFilePath, memoryFilePath):
        '''if instructionState[1].strip() not in ["sw", "s.d"] and self.instructionSet[instructionState[1]] <> "NO_EX":
        Constructor
        '''
        self.outputTable = {}
        self.pipelineConfiguration = self.readConfigFile(configFilePath)
        self.instructionSet = self.readInstructionSet(instructionSetFilePath)
        self.prepareArchitecture(registerFilePath, memoryFilePath)
        self.instructions, self.labels = self.readInstructionsFile(instrFilePath) 
                
        
    def readConfigFile(self, filePath):
        configFile = io.open(filePath)
        cfg = {}
        
        fileLine = configFile.readline()
        while fileLine:
            cfg[fileLine.split(":")[0].lower().strip()] = fileLine.split(":")[1].strip().split(",")
            fileLine = configFile.readline()
        return cfg
    
    def readInstructionSet(self, instructionSetFilePath):
        instructionSet = {}
        instructionSetFile = io.open(instructionSetFilePath)
        fileLine = instructionSetFile.readline().strip()
        while fileLine:
            instructionSet[fileLine.strip().split(',')[0].strip().lower()] = fileLine.strip().split(',')[1].strip()
            fileLine = instructionSetFile.readline().strip()
        return instructionSet
        
    def readInstructionsFile(self, filePath):
        instrFile = io.open(filePath)
        # instructions = defaultdict(dict)
        instructions = {}
        labels = {}
        
        instructionIndex = 1
        
        instruction = instrFile.readline().strip().lower()
        while instruction:
            self.outputTable[str(instructionIndex)] = {
                                                       "IF":0,
                                                       "ID":0,
                                                       "EX":0,
                                                       "WB":0,
                                                       "RAW":False,
                                                       "WAR":False,
                                                       "WAW":False,
                                                       "STRUCT":False
                                                       }
            
            # extract label for instruction if any and record the reference in the label index
            if len(instruction.split(":")) > 1:
                label = instruction.split(":")[0].strip()
                labels[label] = str(instructionIndex)
                # strip label from instruction
                instruction = instruction.split(":")[1].strip()
            
            
            tokens = instruction.split(' ', 1)
            opcode = tokens[0].strip()
            if len(tokens) == 1:
                # no operands present
                operands = ""
            else:  
                # process operands present to extract register operands
                operands = []
                operandTokens = tokens[1].strip().split(',')
                for token in operandTokens:
                    operand = token.strip()
                    patternMatch = re.search("[r,f]\d+", operand)
                    if patternMatch:
                        operands.append(patternMatch.group(0).strip("("))
                    
                
            instructions[str(instructionIndex)] = {
                                                 "opcode": opcode,
                                                 "operands": operands
                                                 }
            instructionIndex += 1
            instruction = instrFile.readline().strip().lower()
            
        
        return instructions, labels

    def prepareArchitecture(self, registerFilePath, memoryFilePath):
        self.clock = 0
        self.executionComplete = False
        
        self.multipathPipeline = {
                                  "MST_SEQ":["IF", "ID", "INT_EX", "MEM", "FP_ADD", "FP_DIV", "FP_MUL", "WB"],
                                  "INT_SEQ":["INT_EX", "MEM"],
                                  "CYCLE_TIMES":{
                                                 "IF": int(self.pipelineConfiguration["i-cache"][0].strip()),
                                                 "ID": 1,
                                                 "INT_EX":1,
                                                 "MEM":int(self.pipelineConfiguration["main memory"][0].strip()),
                                                 "FP_ADD":int(self.pipelineConfiguration["fp adder"][0].strip()),
                                                 "FP_MUL":int(self.pipelineConfiguration["fp multiplier"][0].strip()),
                                                 "FP_DIV":int(self.pipelineConfiguration["fp divider"][0].strip()),
                                                 "WB":1
                                                 },
                                  "IF":Queue.Queue(maxsize=1),
                                  "ID":Queue.Queue(maxsize=1),
                                  "INT_EX":Queue.Queue(maxsize=1),
                                  "MEM":Queue.Queue(maxsize=1),
                                  "FP_ADD":Queue.Queue(maxsize=1),
                                  "FP_MUL":Queue.Queue(maxsize=1),
                                  "FP_DIV":Queue.Queue(maxsize=1),
                                  "WB":Queue.Queue(maxsize=1)
                                  }
        
        if self.pipelineConfiguration["fp adder"][1].strip() == "yes":
            self.multipathPipeline["FP_ADD"].maxsize = int(self.pipelineConfiguration["fp adder"][0].strip())  
            
        if self.pipelineConfiguration["fp multiplier"][1].strip() == "yes":
            self.multipathPipeline["FP_MUL"].maxsize = int(self.pipelineConfiguration["fp multiplier"][0].strip())  
            
        if self.pipelineConfiguration["fp adder"][1].strip() == "yes":
            self.multipathPipeline["FP_DIV"].maxsize = int(self.pipelineConfiguration["fp divider"][0].strip())  
        
        self.initializeRegisterStatusVector()
        self.initializeRegisterFile(registerFilePath)
        self.initializeMemory(memoryFilePath)
    
    def initializeRegisterFile(self, registerFilePath):
        registerFile = io.open(registerFilePath)
        registerIndex = 0
        self.registerFile = {}
        registerValue = registerFile.readline()
        while registerValue:
            self.registerFile["r" + str(registerIndex)] = int(registerValue, 2)
            registerValue = registerFile.readline()
            registerIndex += 1
            
    def initializeMemory(self, memoryFilePath):
        memoryFile = io.open(memoryFilePath)
        memoryWordIndex = 0
        self.dataMemory = {}
        memoryWord = memoryFile.readline()
        while memoryWord:
            self.dataMemory[str(memoryWordIndex)] = int(memoryWord, 2)
            memoryWord = memoryFile.readline()
            memoryWordIndex += 1
    
    def initializeRegisterStatusVector(self):
        '''
        ARGS : none
        DEFN : initializes register write status vector
        '''
        self.register_status = {}
        for index in range(1, 33):
            self.register_status["r" + str(index)] = {"R":0, "W":0}
            self.register_status["f" + str(index)] = {"R":0, "W":0}
    
    def simulateInstructions(self):
        index = 1
        while index <= len(self.instructions) :
            if index == 1:
                self.multipathPipeline["IF"].put(
                                                 [
                                                  index,
                                                  self.instructions[str(index)]["opcode"],
                                                  self.multipathPipeline["CYCLE_TIMES"]["IF"]
                                                  ]
                                                 )
                index += 1  
                
            else:
                self.progressPipeline()
                if self.multipathPipeline["IF"].empty():
                    self.multipathPipeline["IF"].put([
                                                  index,
                                                  self.instructions[str(index)]["opcode"],
                                                  self.multipathPipeline["CYCLE_TIMES"]["IF"] - 1
                                                  ]
                                                 )
                    index += 1
            self.clock += 1
            
        
        # wait for execution completion after initiating all instructions
        while not self.executionComplete:
            self.progressPipeline()
            self.clock += 1
    
    def setRegisterStatus(self, instruction):
        '''
        ARGS : instruction id
        DEFN : method should be called upon instruction issue (at instruction decode stage) to set status of registers used as operands
        '''
        operands = self.instructions[instruction]["operands"]
        opcode = self.instructions[instruction]["opcode"].strip()
        if operands != "":
            if opcode not in ["SW", "S.D"] and self.instructionSet[opcode] <> "NO_EX":
                self.register_status[operands[0].strip()]["W"] += 1
                
    def progressPipeline(self):
        '''
        ARGS : none
        DEFN : method should be called upon all but first clock cycle. It propogates (when possible) instructions through pipeline stages
        ''' 
        emptyStageCount = 0
        
        nextStage = "END"
        pipelineStages = deepcopy(self.multipathPipeline["MST_SEQ"])
        pipelineStages.reverse()
        for currentStage in pipelineStages:
            if not self.multipathPipeline[currentStage].empty():
                instructionState = self.multipathPipeline[currentStage].get()
                if instructionState[2] > 0:
                    # # instruction hasn't completed current stage and persist in this stage for this cycle
                    instructionState[2] -= 1
                    self.multipathPipeline[currentStage].put(instructionState)
                else: 
                    # instruction has completed this stage
                    nextStage = self.getNextStage(instructionState, currentStage)
                    if nextStage != "END":
                        # check for any instruction hazards
                        hazardStatus = self.checkHazards(instructionState[0], nextStage)
                        if not hazardStatus[0]:
                            self.updateOutputTableStageCompletion(instructionState[0], currentStage)
                            self.enqueueInNextStage(instructionState, currentStage, nextStage)
                            
                            # write cycle time for instruction current stage completion to file
                        else:
                            # hazard detected...log hazard in output table
                            self.updateOutputTableHazard(instructionState[0], hazardStatus[1])
                            # stall instruction in current phase
                            self.multipathPipeline[currentStage].put(instructionState)
                    else:
                        # instruction complete. reset write register status vector for destination register
                        # if self.instructions[str(instructionState[0])]["opcode"].strip() not in ["sw", "s.d"]:
                        if instructionState[1].strip() not in ["sw", "s.d"] and self.instructionSet[instructionState[1]] <> "NO_EX":
                            self.register_status[self.instructions[str(instructionState[0])]["operands"][0].strip()]["W"] -= 1
                        self.updateOutputTableStageCompletion(instructionState[0], currentStage)
            else:
                # no instruction in current stage...process next stage
                emptyStageCount += 1
                continue
            
        if emptyStageCount == len(self.multipathPipeline["MST_SEQ"]):
            self.executionComplete = True
    
    def getNextStage(self, instructionState, currentStage):
        '''
        ARGS : current instruction state, current instruction stage
        DEFN : method should be called to retrieve next stage for the instruction. 
        ''' 
        nextStage = ""
        
        if currentStage == "ID":
            # check if instruction is branch
            if self.instructionSet[instructionState[1]] == "NO_EX":
                nextStage = "END"
            # else choose execution path 
            elif self.instructionSet[instructionState[1]] in ["INT", "MEM"]:
                nextStage = "INT_EX"
            elif self.instructionSet[instructionState[1]] == "FP_ADD":
                nextStage = "FP_ADD"
            elif self.instructionSet[instructionState[1]] == "FP_DIV":
                nextStage = "FP_DIV"
            elif self.instructionSet[instructionState[1]] == "FP_MUL":
                nextStage = "FP_MUL"
        elif currentStage == "INT_EX":
            # if current stage in integer execution then next stage is memory
            nextStage = "MEM"
        elif currentStage in ["MEM", "FP_ADD", "FP_DIV", "FP_MUL"]:
            # if current stage is execution then next stage is write back
            nextStage = "WB"
        elif currentStage == "WB":
            nextStage = "END"
        else:
            nextStage = "ID"
            
        return nextStage  
    
    def checkHazards(self, instruction, nextStage): 
        '''
        ARGS : instruction id, next instruction stage
        DEFN : method checks for instruction hazards. should be called when instruction completes current stage and before propogation to next stage.
        '''
        hazards = []
        try:
            if self.multipathPipeline[nextStage].full():  # structural hazard
                hazards.append("SH")
            if nextStage == "ID":
                if not self.register_status[self.instructions[instruction]["operands"][0].strip()] == 0:
                    if self.instructions[instruction]["opcode"].strip() in ["sw", "s.d"] or self.instructionSet[instruction] == "NO_EX":
                        hazards.append("RAW")
                elif not self.register_status[self.instructions[instruction]["operands"][1].strip()] == 0:
                    hazards.append("RAW")
                elif not self.register_status[self.instructions[instruction]["operands"][2].strip()] == 0:
                    hazards.append("RAW")
            elif nextStage == "WB":
                if self.instructions[instruction]["opcode"] not in ["SW", "S.D"] and self.instructionSet[instruction] == "NO_EX":
                    if not self.register_status[self.instructions[instruction]["operands"][0].strip()] == 1:
                        hazards.append("WAW")
                    # elif self.register_status[self.instructions[instruction]["operands"][0].strip()] == "R":
                        # return [True, "WAR"]
            
            if len(hazards) == 0:
                return [False]
            else:
                return [True, hazards]
        except:
            return [False]
    
    def enqueueInNextStage(self, instructionState, currentStage, nextStage):
        if nextStage == "ID":
            # set destination register operand status to write
            # if self.instructions[str(instructionState[0])]["opcode"].strip() not in ["sw", "s.d"] and self.instructionSet[]:
            if instructionState[1].strip() not in ["sw", "s.d"] and self.instructionSet[instructionState[1]] <> "NO_EX":
                self.register_status[self.instructions[str(instructionState[0])]["operands"][0].strip()]["W"] += 1
        
        # special check for no execution instructions
        if self.instructionSet[instructionState[1]] <> "MEM" and nextStage == "MEM":
            self.multipathPipeline[nextStage].put(
                                              [
                                               instructionState[0],
                                               instructionState[1],
                                               0
                                               ]
                                              )
        else:
            self.multipathPipeline[nextStage].put(
                                              [
                                               instructionState[0],
                                               instructionState[1],
                                               self.multipathPipeline["CYCLE_TIMES"][nextStage] - 1
                                               ]
                                              )
    
    def updateOutputTableStageCompletion(self, instructionIndex, currentStage):
        if currentStage == "INT_EX":
            pass
        elif currentStage in ["IF", "ID", "WB"]:
            self.outputTable[str(instructionIndex)][currentStage] = self.clock - 1
        else:
            self.outputTable[str(instructionIndex)]["EX"] = self.clock - 1
            
    def updateOutputTableHazard(self, instructionIndex, hazards):
        for hazard in hazards:
            self.outputTable[str(instructionIndex)][hazard] = True
