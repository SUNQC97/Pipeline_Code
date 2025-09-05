function setAndCheckParameter(paramPath, setValue) {
  var returnStatus = new VJSStatus();
  var readValue = new VJSVariant();
  VModelManipulationInterface.setParameterByHierarchicalName(paramPath, setValue, returnStatus);
  VModelManipulationInterface.getParameterByHierarchicalName(paramPath, readValue, returnStatus);
  if (returnStatus.hasSucceeded()) {
    VLogInterface.emitInformationMessage("Set: " + paramPath + " = " + readValue.getValue(), false);
  } else {
    VLogInterface.emitErrorMessage("Failed: " + paramPath + " → " + returnStatus.createFormattedErrorMessage(), false);
  }
}

var valuesToSet = {
  "par_0": 0,
  "par_1": 0,
  "par_2": 0,
  "par_3": 0,
  "par_4": 0,
  "par_5": 0,
  "par_6": 320,
  "par_7": 225,
  "par_8": 225,
  "par_9": 65,
  "par_10": 0,
  "par_11": 0,
  "par_13": -90,
  "par_14": 0,
  "par_20": 0,
  "par_21": 0,
  "par_22": 0,
  "par_23": 0,
  "par_24": 0,
  "par_25": 0,
  "par_30": 0,
  "par_31": 35,
  "Axis_1.ratio": 0.017453292519943295,
  "Axis_1.s_min": -180,
  "Axis_1.s_max": 180,
  "Axis_1.s_init": 0,
  "Axis_1.v_max": 555,
  "Axis_1.a_max": 1000,
  "Axis_2.ratio": 0.017453292519943295,
  "Axis_2.s_min": -125,
  "Axis_2.s_max": 125,
  "Axis_2.s_init": 0,
  "Axis_2.v_max": 475,
  "Axis_2.a_max": 1250,
  "Axis_3.ratio": 0.017453292519943295,
  "Axis_3.s_min": -138,
  "Axis_3.s_max": 138,
  "Axis_3.s_init": 90,
  "Axis_3.v_max": 585,
  "Axis_3.a_max": 1500,
  "Axis_4.ratio": 0.017453292519943295,
  "Axis_4.s_min": -270,
  "Axis_4.s_max": 270,
  "Axis_4.s_init": 0,
  "Axis_4.v_max": 1035,
  "Axis_4.a_max": 2500,
  "Axis_5.ratio": 0.017453292519943295,
  "Axis_5.s_min": -120,
  "Axis_5.s_max": 133.5,
  "Axis_5.s_init": 90,
  "Axis_5.v_max": 1135,
  "Axis_5.a_max": 2500,
  "Axis_6.ratio": 0.017453292519943295,
  "Axis_6.s_min": -270,
  "Axis_6.s_max": 270,
  "Axis_6.s_init": 0,
  "Axis_6.v_max": 1575,
  "Axis_6.a_max": 3000,
};
for (var key in valuesToSet) {
  var path = "[Block Diagram].[OSACA2__St?ubli__TX2-40-HB__1_0].[RobotController].[" + key + "]";
  setAndCheckParameter(path, valuesToSet[key]);
}