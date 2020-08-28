import React from 'react'
import { Accordion } from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';
import AccordionSummary from '@material-ui/core/AccordionSummary';
import AccordionDetails from '@material-ui/core/AccordionDetails';
import Typography from '@material-ui/core/Typography';
import ExpandMoreIcon from '@material-ui/icons/ExpandMore';

const useStyles = makeStyles((theme) => ({
  root: {
    flexGrow: 1,
  },
  paper: {
    padding: theme.spacing(2),
    textAlign: 'center',
    color: theme.palette.text.primary,
  },
  icon: {
    paddingRight: '1rem',
  },
  heading: {
    fontSize: theme.typography.pxToRem(15),
    fontWeight: theme.typography.fontWeightRegular,
  },
}));


function ChannelAccordion(props) {
  const classes = useStyles();
  const { icon, name } = props;

  return (
    <Accordion>
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        aria-controls="panel1a-content"
        id="panel1a-header"
      >
        <img
          src={icon}
          className={classes.icon}
          alt="TelegramIcon"
        />
        <Typography
          style={{ textAlign: 'center' }}
          variant="h5"
          align="center"
          gutterBottom
        >
          {name}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <h1>Chicken</h1>
      </AccordionDetails>
    </Accordion>
  )
}

export default ChannelAccordion;